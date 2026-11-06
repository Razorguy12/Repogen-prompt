import datetime as dt

from database import FinalReport, SessionLocal
from tests.helpers import client, finalize, make_draft, make_user


def test_new_patient_finalize_records_timestamps_and_study_date():
    user, h = make_user()
    draft = make_draft(user)
    r = finalize(h, draft.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["study_date"] == "2026-10-23"
    assert body["finalized_at"].endswith("Z") and body["created_at"].endswith("Z")
    assert body["patient"]["full_name"] == "Ramesh Kumar"
    assert body["final_text"].startswith("## CHEST RADIOGRAPH")
    assert body["prompt_version"] == "v2" and body["model_id"] == "test-model"
    # Draft is locked afterwards.
    assert client.patch(f"/api/reports/{draft.id}/draft", json={"selected": "concise"}, headers=h).status_code == 400
    assert client.patch(f"/api/reports/{draft.id}/status", json={"status": "draft"}, headers=h).status_code == 409


def test_duplicate_guard_then_use_existing_or_create_anyway():
    user, h = make_user()
    assert finalize(h, make_draft(user).id).status_code == 200
    second = make_draft(user)
    r = finalize(h, second.id, new_patient={"full_name": "  mr. ramesh   KUMAR ", "gender": "Male"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "possible_duplicate" and len(detail["matches"]) == 1
    existing_id = detail["matches"][0]["id"]
    assert finalize(h, second.id, new_patient=None, patient_id=existing_id).status_code == 200
    third = make_draft(user)
    r = finalize(h, third.id, new_patient={"full_name": "Ramesh Kumar", "gender": "Male"}, create_new_anyway=True)
    assert r.status_code == 200 and r.json()["patient"]["id"] != existing_id


def test_identifier_clash_cannot_be_overridden():
    user, h = make_user()
    finalize(h, make_draft(user).id, new_patient={"full_name": "A One", "patient_identifier": "UH 01", "gender": "Male"})
    r = finalize(h, make_draft(user).id, create_new_anyway=True,
                 new_patient={"full_name": "B Two", "patient_identifier": "uh01", "gender": "Female"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "identifier_in_use"


def test_unacknowledged_flags_block_finalization():
    user, h = make_user()
    draft = make_draft(user, flags=["Laterality not stated", "Fetal sex omitted"])
    assert finalize(h, draft.id).status_code == 422
    partial = [{"index": 0, "acknowledged_at": "2026-11-06T10:00:00Z"}]
    assert finalize(h, draft.id, flag_acknowledgements=partial).status_code == 422
    both = partial + [{"index": 1, "acknowledged_at": "2026-11-06T10:00:05Z"}]
    r = finalize(h, draft.id, flag_acknowledgements=both)
    assert r.status_code == 200
    acks = r.json()["flag_acknowledgements"]
    assert [a["flag"] for a in acks] == ["Laterality not stated", "Fetal sex omitted"]
    assert r.json()["flags_acknowledged_at"]


def test_server_side_validation():
    user, h = make_user()
    draft = make_draft(user)
    tomorrow = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    assert finalize(h, draft.id, study_date=tomorrow).status_code == 422
    assert finalize(h, draft.id, age_value=131).status_code == 422
    assert finalize(h, draft.id, age_value=400, age_unit="days").status_code == 422
    assert finalize(h, draft.id, approved=False).status_code == 422
    assert finalize(h, draft.id, exam={"modality": "UNSPECIFIED", "region": "Chest",
                                       "laterality": "Not applicable"}).status_code == 422
    assert finalize(h, draft.id, selected_variant="detailed").status_code == 409
    assert finalize(h, draft.id, new_patient={"full_name": "A", "gender": "Male"}).status_code == 422
    assert finalize(h, draft.id, age_value=3, age_unit="days").status_code == 200
    assert finalize(h, draft.id).status_code == 409  # already finalized


def test_amendment_creates_linked_version_and_original_is_unchanged():
    user, h = make_user()
    fr = finalize(h, make_draft(user).id).json()
    r = client.post(f"/api/final-reports/{fr['id']}/amend", json={"final_text": "## CHEST\nAmended text."}, headers=h)
    assert r.status_code == 200
    amended = r.json()
    assert amended["status"] == "amended" and amended["amends_report_id"] == fr["id"]
    original = client.get(f"/api/final-reports/{fr['id']}", headers=h).json()
    assert original["superseded_by_id"] == amended["id"]
    assert original["final_text"] == fr["final_text"]
    newest = client.get(f"/api/final-reports/{amended['id']}", headers=h).json()
    assert [v["id"] for v in newest["previous_versions"]] == [fr["id"]]
    # Amending a superseded version is refused; listing shows only latest by default.
    assert client.post(f"/api/final-reports/{fr['id']}/amend", json={"final_text": "x"}, headers=h).status_code == 409
    listed = client.get(f"/api/patients/{fr['patient']['id']}/final-reports", headers=h).json()
    assert [x["id"] for x in listed] == [amended["id"]]


def test_no_api_route_edits_final_text():
    paths = {(m, r.path) for r in __import__("main").app.routes for m in getattr(r, "methods", [])}
    assert not any(p.startswith("/api/final-reports/{report_id}") and m in {"PUT", "PATCH", "DELETE"}
                   for m, p in paths)


def test_age_suggestion_from_previous_report():
    user, h = make_user()
    fr = finalize(h, make_draft(user).id, age_value=45, study_date="2024-10-23").json()
    r = client.get(f"/api/patients/{fr['patient']['id']}/age-suggestion?study_date=2026-10-22", headers=h)
    assert r.json() == {"value": 46, "unit": "years"}


def test_access_scoping_between_doctors():
    a, ha = make_user("Dr A")
    b, hb = make_user("Dr B")
    fr = finalize(ha, make_draft(a).id).json()
    pid = fr["patient"]["id"]
    assert client.get(f"/api/final-reports/{fr['id']}", headers=hb).status_code == 404
    assert client.get(f"/api/patients/{pid}", headers=hb).status_code == 404
    assert client.get("/api/patients?q=ramesh", headers=hb).json() == []
    assert client.post(f"/api/final-reports/{fr['id']}/amend", json={"final_text": "x"}, headers=hb).status_code == 404
    # B cannot finalize A's draft, nor attach A's patient to B's draft.
    assert finalize(hb, make_draft(a).id).status_code == 404
    assert finalize(hb, make_draft(b).id, new_patient=None, patient_id=pid).status_code == 404


def test_final_text_column_immutable_via_orm():
    user, h = make_user()
    fr = finalize(h, make_draft(user).id).json()
    db = SessionLocal()
    row = db.get(FinalReport, fr["id"])
    row.final_text = "tampered"
    try:
        db.commit()
        raised = False
    except Exception:
        db.rollback()
        raised = True
    db.close()
    assert raised
