"""Findings, report text and patient data stay out of logs and model input."""
import logging

import main
import model.model as m
import rate_limit
from database import AuditEvent, SessionLocal
from tests.fixtures import VALID_GENERATION
from tests.helpers import client, make_user

SENTINEL = "SENTINELFINDING lesion"


def test_generation_success_and_failure_log_no_findings(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    _, h = make_user()
    rate_limit.reset()
    monkeypatch.setattr(main.model, "generate_reports",
                        lambda *a, **k: m.ReportAlternatives.model_validate(VALID_GENERATION))
    assert client.post("/api/generate-alternatives", json={"prompt": SENTINEL}, headers=h).status_code == 200

    def boom(*a, **k):
        raise m.GenerationError(SENTINEL)

    monkeypatch.setattr(main.model, "generate_reports", boom)
    assert client.post("/api/generate-alternatives", json={"prompt": SENTINEL}, headers=h).status_code == 502
    assert "SENTINELFINDING" not in caplog.text
    db = SessionLocal()
    assert all("SENTINELFINDING" not in str(e.details) for e in db.query(AuditEvent).all())
    db.close()


def test_structured_flow_does_not_send_patient_info(monkeypatch):
    seen = {}

    def capture(text):
        seen["text"] = text
        raise RuntimeError("stop")

    monkeypatch.setattr(main.model, "generate_report", capture)
    _, h = make_user()
    rate_limit.reset()
    client.post("/api/generate-report", headers=h, json={
        "patient_info": "Ramesh Kumar 45M MRN123", "study_info": "CT brain", "radiologist_findings": "Normal"})
    assert "CT brain" in seen["text"] and "Ramesh" not in seen["text"] and "MRN123" not in seen["text"]
