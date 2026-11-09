from sqlalchemy import (create_engine, Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, text,
                        JSON, Index, UniqueConstraint, CheckConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import datetime

load_dotenv()

# Use the DATABASE_URL from .env. If not set, raise an error or fallback to a default.
# The user asked for postgresql, so we expect something like:
# postgresql://user:password@localhost:5432/radiology_db
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not SQLALCHEMY_DATABASE_URL:
    # We fallback to sqlite for testing purposes if they haven't set the postgres URL yet
    print("WARNING: DATABASE_URL not found in environment, falling back to sqlite")
    SQLALCHEMY_DATABASE_URL = "sqlite:///./radiology.db"
    
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    report_quota_start = Column(Integer, default=0, nullable=False)
    custom_report_format = Column(Text, nullable=True)
    
    reports = relationship("Report", back_populates="user")

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    patient_id = Column(String, index=True)
    patient_name = Column(String)
    modality = Column(String)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    report_data = Column(Text)  # JSON string of the complete report
    input_params = Column(Text, nullable=True)  # JSON string of original form inputs
    scan_image = Column(Text, nullable=True)  # Base64 or URL of uploaded scan image
    scan_image_name = Column(String, nullable=True)  # Original filename

    user = relationship("User", back_populates="reports")


class AuditEvent(Base):
    """Append-only application audit record. Never store clinical content here."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(80), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="SUCCESS")
    resource_type = Column(String(80), nullable=True)
    resource_id = Column(String(128), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    request_id = Column(String(64), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    details = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_user_id", "user_id"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_status", "status"),
        Index("ix_audit_events_resource_id", "resource_id"),
    )

def utcnow() -> datetime.datetime:
    """Timezone-aware UTC now. All new tables store timestamptz."""
    return datetime.datetime.now(datetime.timezone.utc)


class UTCDateTime(TypeDecorator):
    """timestamptz that always binds UTC and always returns aware UTC values.

    Postgres does this natively; SQLite would otherwise drop the offset and
    keep local wall-clock time. Naive inputs are rejected so a local time can
    never be stored by mistake.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        value = value.astimezone(datetime.timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(datetime.timezone.utc)


def iso_utc(value):
    """Serialise a datetime as ISO-8601 UTC with a trailing Z.

    Legacy `reports` columns are naive but hold UTC (written by utcnow()),
    so naive values are tagged as UTC rather than converted.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return value.isoformat()


JSONType = JSON().with_variant(JSONB, "postgresql")
GENDERS = ("Male", "Female", "Other", "Not stated")
MODALITY_VALUES = ("XR", "CT", "MRI", "US", "DOPPLER", "MAMMO", "FLUORO", "OTHER", "UNSPECIFIED")
AGE_UNITS = ("years", "months", "days")


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TimestampMixin:
    # Set by the server/ORM only; never accepted from clients.
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow, server_default=func.now())
    updated_at = Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow,
                        server_default=func.now())


class Patient(TimestampMixin, Base):
    """A patient, private to the doctor who created it (owner_doctor_id)."""
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    owner_doctor_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    patient_identifier = Column(String(64), nullable=True)            # MRN / UHID as entered
    patient_identifier_normalized = Column(String(64), nullable=True)  # upper-case, no spaces; for matching
    full_name = Column(String(100), nullable=False)
    full_name_normalized = Column(String(100), nullable=False)
    gender = Column(String(16), nullable=False)

    __table_args__ = (
        UniqueConstraint("owner_doctor_id", "patient_identifier_normalized", name="uq_patients_owner_identifier"),
        CheckConstraint(_in("gender", GENDERS), name="ck_patients_gender"),
        Index("ix_patients_full_name_normalized", "full_name_normalized"),
    )


class FinalReport(TimestampMixin, Base):
    """An immutable, signed report. Amendments are new rows (amends_report_id)."""
    __tablename__ = "final_reports"

    id = Column(Integer, primary_key=True)
    draft_id = Column(Integer, ForeignKey("reports.id", ondelete="RESTRICT"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="final")
    amends_report_id = Column(Integer, ForeignKey("final_reports.id", ondelete="RESTRICT"), nullable=True, index=True)
    selected_variant = Column(String(16), nullable=False)
    final_text = Column(Text, nullable=False)
    final_sections = Column(JSONType, nullable=True)
    exam_modality = Column(String(16), nullable=False)
    exam_region = Column(String(120), nullable=False)
    exam_laterality = Column(String(32), nullable=False)
    exam_title = Column(String(200), nullable=False)
    patient_age_at_study = Column(Integer, nullable=False)
    age_unit = Column(String(8), nullable=False)
    study_date = Column(Date, nullable=False)
    source_input = Column(Text, nullable=True)
    flags = Column(JSONType, nullable=False, default=list)
    flag_acknowledgements = Column(JSONType, nullable=False, default=list)  # [{flag, acknowledged_at}]
    flags_acknowledged_at = Column(UTCDateTime(), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    model_id = Column(String(120), nullable=True)
    finalized_at = Column(UTCDateTime(), nullable=False, default=utcnow)

    patient = relationship("Patient")
    doctor = relationship("User", foreign_keys=[doctor_id])

    __table_args__ = (
        CheckConstraint("status IN ('final', 'amended')", name="ck_final_reports_status"),
        CheckConstraint("selected_variant IN ('concise', 'standard', 'detailed')", name="ck_final_reports_variant"),
        CheckConstraint(_in("exam_modality", MODALITY_VALUES), name="ck_final_reports_modality"),
        CheckConstraint(_in("age_unit", AGE_UNITS), name="ck_final_reports_age_unit"),
        CheckConstraint("(status = 'amended') = (amends_report_id IS NOT NULL)", name="ck_final_reports_amend_link"),
        Index("ix_final_reports_patient_study_date", "patient_id", "study_date"),
        Index("ix_final_reports_exam_modality", "exam_modality"),
        Index("ix_final_reports_exam_region", "exam_region"),
    )


class ReportFlag(Base):
    """A review item on a draft, shared by all three alternatives."""
    __tablename__ = "report_flags"

    id = Column(Integer, primary_key=True)
    draft_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(32), nullable=False)
    severity = Column(String(8), nullable=False)
    raw_text = Column(Text, nullable=False)
    items = Column(JSONType, nullable=False, default=list)  # [{text, status}]
    source = Column(String(8), nullable=False)
    requires_review = Column(Boolean, nullable=False)
    status = Column(String(16), nullable=False, default="open")
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(UTCDateTime(), nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('open', 'confirmed', 'corrected', 'not_applicable')", name="ck_report_flags_status"),
        CheckConstraint("source IN ('model', 'server')", name="ck_report_flags_source"),
    )


class Comparison(TimestampMixin, Base):
    __tablename__ = "comparisons"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True)
    baseline_report_id = Column(Integer, ForeignKey("final_reports.id", ondelete="RESTRICT"), nullable=False, index=True)
    followup_report_id = Column(Integer, ForeignKey("final_reports.id", ondelete="RESTRICT"), nullable=False, index=True)
    interval_days = Column(Integer, nullable=False)
    result = Column(JSONType, nullable=False)
    edited_summary = Column(Text, nullable=True)
    edited_impression = Column(JSONType, nullable=True)
    status = Column(String(8), nullable=False, default="draft")
    prompt_version = Column(String(64), nullable=True)
    model_id = Column(String(120), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'saved')", name="ck_comparisons_status"),
        CheckConstraint("baseline_report_id <> followup_report_id", name="ck_comparisons_distinct"),
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


MIGRATION_LOCK_ID = 724_001  # arbitrary constant for pg_advisory_xact_lock


def upgrade_schema(db_engine=None):
    """Apply Alembic migrations up to head.

    Safe to call from every worker on startup: on Postgres an advisory lock
    serialises concurrent callers, and Alembic skips revisions already applied.
    """
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    db_engine = db_engine or engine
    cfg = Config(str(Path(__file__).with_name("alembic.ini")))
    with db_engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIGRATION_LOCK_ID})
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def run_migrations(db_engine=None):
    """Backward-compatible alias; schema changes now live in alembic/versions."""
    upgrade_schema(db_engine)
