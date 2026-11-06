"""API test helpers: users, tokens and drafts in the isolated test database."""
import datetime as dt
import itertools
import json

from fastapi.testclient import TestClient

import auth
import main
import rate_limit
from database import Report, SessionLocal, User
from tests.fixtures import VALID_GENERATION

_seq = itertools.count(1)
client = TestClient(main.app)


def make_user(name="Dr Test"):
    n = next(_seq)
    db = SessionLocal()
    user = User(name=f"{name} {n}", username=f"doc{n}", email=f"doc{n}@example.test",
                hashed_password="x", is_admin=True)  # admin: bypasses the 10-report quota only
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user, {"Authorization": f"Bearer {auth.create_access_token({'sub': user.username})}"}


def make_draft(user, flags=None, exam=None, selected="standard", full_report=None):
    gen = json.loads(json.dumps(VALID_GENERATION))
    if full_report:
        for r in gen["reports"]:
            r["full_report"] = full_report
    db = SessionLocal()
    now = dt.datetime.utcnow()
    draft = Report(user_id=user.id, patient_id="R-test", patient_name="CHEST RADIOGRAPH", modality="X-ray",
                   status="draft", created_at=now, updated_at=now, report_data="{}",
                   input_params=json.dumps({
                       "kind": "prompt", "prompt": "CXR - lungs clear", "report_format": "", "selected": selected,
                       "alternatives": gen["reports"], "exam": exam or gen["exam"], "flags": flags or [],
                       "prompt_version": "v2", "model_id": "test-model",
                   }))
    db.add(draft)
    db.commit()
    db.refresh(draft)
    db.close()
    return draft


def finalize_body(**overrides):
    body = {
        "selected_variant": "standard",
        "new_patient": {"full_name": "Ramesh Kumar", "patient_identifier": None, "gender": "Male"},
        "age_value": 45, "age_unit": "years", "study_date": "2026-10-23",
        "exam": {"modality": "XR", "region": "Chest", "laterality": "Not applicable"},
        "flag_acknowledgements": [], "approved": True,
    }
    body.update(overrides)
    return body


def finalize(user_headers, draft_id, **overrides):
    rate_limit.reset()
    return client.post(f"/api/reports/{draft_id}/finalize", json=finalize_body(**overrides), headers=user_headers)
