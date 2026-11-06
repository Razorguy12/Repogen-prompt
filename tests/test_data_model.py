"""Migrations, timestamps and immutability.

Runs on SQLite by default. Set TEST_PG_URL to an empty Postgres database to
run the same checks there (e.g. postgresql://postgres@127.0.0.1:54329/x).
"""
import datetime as dt
import os
import tempfile

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

import database
from database import FinalReport, Patient, Report, User, iso_utc

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _cfg(conn):
    cfg = Config("alembic.ini")
    cfg.attributes["connection"] = conn
    return cfg


def _urls():
    tmp = tempfile.mkdtemp()
    urls = [f"sqlite:///{tmp}/mig.db"]
    if os.getenv("TEST_PG_URL"):
        urls.append(os.environ["TEST_PG_URL"])
    return urls


@pytest.fixture(params=_urls())
def engine(request):
    eng = sa.create_engine(request.param)
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), "head")
    yield eng
    with eng.begin() as conn:
        command.downgrade(_cfg(conn), "base")
        for table in ("audit_events", "reports", "users", "alembic_version"):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE" if eng.dialect.name == "postgresql"
                                 else f"DROP TABLE IF EXISTS {table}"))
    eng.dispose()


def _seed(session):
    user = User(name="Dr A", username="dra", email="a@x", hashed_password="h")
    session.add(user)
    session.flush()
    draft = Report(user_id=user.id, status="draft", report_data="{}", input_params="{}",
                   created_at=dt.datetime(2026, 1, 1, 6, 0), updated_at=dt.datetime(2026, 1, 1, 6, 0))
    patient = Patient(owner_doctor_id=user.id, full_name="Ramesh Kumar", full_name_normalized="ramesh kumar",
                      gender="Male")
    session.add_all([draft, patient])
    session.flush()
    return user, draft, patient


def _final(user, draft, patient, **kw):
    values = dict(draft_id=draft.id, patient_id=patient.id, doctor_id=user.id, status="final",
                  selected_variant="standard", final_text="## CHEST\nClear.", exam_modality="XR",
                  exam_region="Chest", exam_laterality="Not applicable", exam_title="CHEST RADIOGRAPH",
                  patient_age_at_study=40, age_unit="years", study_date=dt.date(2026, 11, 6),
                  flags=[], flag_acknowledgements=[])
    values.update(kw)
    return FinalReport(**values)


def test_downgrade_then_upgrade_is_clean(engine):
    with engine.begin() as conn:
        command.downgrade(_cfg(conn), "0001_baseline")
        assert "patients" not in sa.inspect(conn).get_table_names()
        command.upgrade(_cfg(conn), "head")
        assert {"patients", "final_reports", "comparisons"} <= set(sa.inspect(conn).get_table_names())


def test_existing_draft_rows_survive_migration_cycle(engine):
    with Session(engine) as s:
        _, draft, _ = _seed(s)
        s.commit()
        draft_id = draft.id
    with engine.begin() as conn:
        command.downgrade(_cfg(conn), "0001_baseline")
        command.upgrade(_cfg(conn), "head")
    with Session(engine) as s:
        assert s.get(Report, draft_id).input_params == "{}"


def test_timestamp_round_trip_ist(engine):
    """17:31 IST is stored as 12:01 UTC and displayed (by the client) as 17:31 IST."""
    with Session(engine) as s:
        user, draft, patient = _seed(s)
        fr = _final(user, draft, patient, finalized_at=dt.datetime(2026, 11, 6, 17, 31, tzinfo=IST))
        s.add(fr)
        s.commit()
        fr_id = fr.id
    with Session(engine) as s:
        stored = s.get(FinalReport, fr_id).finalized_at
        assert iso_utc(stored) == "2026-11-06T12:01:00Z"
        aware = stored if stored.tzinfo else stored.replace(tzinfo=dt.timezone.utc)
        assert aware.astimezone(IST).strftime("%H:%M") == "17:31"


def test_server_sets_created_and_updated(engine):
    with Session(engine) as s:
        _, _, patient = _seed(s)
        s.commit()
        assert patient.created_at is not None and patient.updated_at is not None


def test_final_text_is_immutable_in_database(engine):
    with Session(engine) as s:
        user, draft, patient = _seed(s)
        fr = _final(user, draft, patient)
        s.add(fr)
        s.commit()
        fr_id = fr.id
    with engine.connect() as conn:
        with pytest.raises(sa.exc.DBAPIError):
            conn.execute(sa.text("UPDATE final_reports SET final_text = 'tampered' WHERE id = :i"), {"i": fr_id})
            conn.commit()


def test_amendment_link_constraint(engine):
    with Session(engine) as s:
        user, draft, patient = _seed(s)
        s.add(_final(user, draft, patient, status="amended"))  # amended without amends_report_id
        with pytest.raises(sa.exc.IntegrityError):
            s.commit()


def test_identifier_unique_per_doctor(engine):
    with Session(engine) as s:
        user, _, _ = _seed(s)
        for _ in range(2):
            s.add(Patient(owner_doctor_id=user.id, full_name="X", full_name_normalized="x", gender="Other",
                          patient_identifier="mrn1", patient_identifier_normalized="MRN1"))
        with pytest.raises(sa.exc.IntegrityError):
            s.commit()


def test_iso_utc_tags_naive_values():
    assert iso_utc(dt.datetime(2026, 11, 6, 12, 1)) == "2026-11-06T12:01:00Z"
