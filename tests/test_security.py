import json

import main
import model.model as m
import rate_limit
from database import AuditEvent, SessionLocal
from tests.fixtures import generation
from tests.helpers import client, finalize, make_draft, make_user


def test_generation_is_rate_limited(monkeypatch):
    rate_limit.reset()
    monkeypatch.setattr(main.model, "generate_reports",
                        lambda *a, **k: m.ReportAlternatives.model_validate(generation()))
    _, h = make_user()
    codes = [client.post("/api/generate-alternatives", json={"prompt": "CXR - clear"}, headers=h).status_code
             for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
    rate_limit.reset()


def test_generated_draft_stores_v2_metadata(monkeypatch):
    rate_limit.reset()
    monkeypatch.setattr(main.model, "generate_reports",
                        lambda *a, **k: m.ReportAlternatives.model_validate(generation(flags=["Check side"])))
    _, h = make_user()
    body = client.post("/api/generate-alternatives", json={"prompt": "CXR - clear"}, headers=h).json()
    assert body["flags"] == ["Check side"] and body["exam"]["modality"] == "XR"
    assert body["prompt_version"] == "v2+trim" and body["created_at"].endswith("Z")


def test_generation_failure_returns_clear_error_and_saves_nothing(monkeypatch):
    rate_limit.reset()

    def boom(*a, **k):
        raise m.GenerationError("bad")
    monkeypatch.setattr(main.model, "generate_reports", boom)
    user, h = make_user()
    r = client.post("/api/generate-alternatives", json={"prompt": "CXR"}, headers=h)
    assert r.status_code == 502 and "Nothing was saved" in r.json()["detail"]
    assert client.get("/api/reports", headers=h).json() == []


def test_audit_events_contain_no_patient_data():
    user, h = make_user()
    fr = finalize(h, make_draft(user).id, new_patient={"full_name": "Zeta Unique", "patient_identifier": "MRN-ZZ9",
                                                         "gender": "Female"}).json()
    db = SessionLocal()
    events = db.query(AuditEvent).filter(AuditEvent.user_id == user.id).all()
    db.close()
    types = {e.event_type for e in events}
    assert {"PATIENT_CREATED", "REPORT_FINALIZED"} <= types
    dumped = json.dumps([[e.event_type, e.resource_id, e.details] for e in events])
    assert "Zeta" not in dumped and "MRN-ZZ9" not in dumped
    assert str(fr["id"]) in dumped
