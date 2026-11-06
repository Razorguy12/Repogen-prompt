import json

import pytest

import model.comparison as cmp
from tests.fixtures import FakeClient
from tests.helpers import client, finalize, make_draft, make_user

VALID = {
    "comparison_title": "Comparison of Chest Radiographs",
    "interval_days": 14,
    "examinations_comparable": True,
    "summary": "The right lower zone opacity has resolved.",
    "changes": [
        {"finding": "Heart size", "category": "STABLE", "baseline": "Normal", "follow_up": "Normal", "note": ""},
        {"finding": "Right lower zone opacity", "category": "RESOLVED", "baseline": "Opacity",
         "follow_up": "Lung fields clear", "note": ""},
    ],
    "comparison_impression": ["Interval resolution of right lower zone opacity."],
    "limitations": [],
    "flags": [],
}


def test_valid_comparison_parses_and_is_reordered():
    result, adjusted = cmp.finalize_result(cmp.parse_comparison(json.dumps(VALID)), 14)
    assert not adjusted
    assert [c.category for c in result.changes] == ["RESOLVED", "STABLE"]


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("summary"),
    lambda d: d["changes"][0].update(category="BETTER"),
    lambda d: d.update(interval_days="fourteen"),
    lambda d: d.update(limitations=None),
])
def test_invalid_comparisons_rejected(mutate):
    data = json.loads(json.dumps(VALID))
    mutate(data)
    with pytest.raises(ValueError):
        cmp.parse_comparison(json.dumps(data))


def test_interval_is_overwritten_with_computed_value():
    data = dict(VALID, interval_days=30)
    result, adjusted = cmp.finalize_result(cmp.parse_comparison(json.dumps(data)), 14)
    assert adjusted and result.interval_days == 14


def test_comparison_retries_once():
    fake = FakeClient(["nope", VALID])
    side = cmp.ExamSide(modality="XR", region="Chest", laterality="Not applicable", text="x")
    result, attempts, _ = cmp.generate_comparison(side, side, 14, client=fake)
    assert attempts == 2 and len(fake.completions.calls) == 2


def _two_finals(h, user, name="Ramesh Kumar", ident="UH77", texts=("RLZ opacity.", "Lung fields clear.")):
    a = finalize(h, make_draft(user, full_report=f"## CHEST\nPatient {name}, {ident}. {texts[0]}").id,
                 study_date="2026-10-23", create_new_anyway=True,
                 new_patient={"full_name": name, "patient_identifier": ident, "gender": "Male"}).json()
    b = finalize(h, make_draft(user, full_report=f"## CHEST\n{texts[1]}").id, study_date="2026-11-06",
                 new_patient=None, patient_id=a["patient"]["id"]).json()
    return a, b


def test_end_to_end_privacy_baseline_order_and_save(monkeypatch):
    user, h = make_user()
    a, b = _two_finals(h, user)
    fake = FakeClient([VALID])
    monkeypatch.setattr(cmp.base, "Groq", lambda api_key: fake)

    # Pass follow-up first: server assigns baseline by study_date.
    r = client.post("/api/comparisons", json={"report_ids": [b["id"], a["id"]]}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["baseline_report_id"] == a["id"] and data["interval_days"] == 14

    sent = json.dumps(fake.completions.calls[0]["messages"])
    for secret in ("Ramesh", "Kumar", "UH77", "Male"):
        assert secret not in sent
    assert "INTERVAL_DAYS: 14" in sent and "BASELINE (modality: XR, region: Chest" in sent

    r = client.patch(f"/api/comparisons/{data['id']}", headers=h,
                     json={"edited_summary": "Edited.", "edited_impression": ["One"], "status": "saved"})
    assert r.json()["status"] == "saved" and r.json()["edited_summary"] == "Edited."
    hist = client.get(f"/api/patients/{a['patient']['id']}/comparisons", headers=h).json()
    assert [c["id"] for c in hist] == [data["id"]]
    assert hist[0]["baseline_study_date"] == "2026-10-23"
    fr = client.get(f"/api/final-reports/{a['id']}", headers=h).json()
    assert [c["id"] for c in fr["comparisons"]] == [data["id"]]

    fake.completions.outputs.append(VALID)
    regen = client.post(f"/api/comparisons/{data['id']}/regenerate", headers=h).json()
    assert regen["id"] != data["id"] and regen["status"] == "draft"
    assert client.get(f"/api/comparisons/{data['id']}", headers=h).json()["status"] == "saved"


def test_comparison_scoping_and_same_patient_rule(monkeypatch):
    a_user, ha = make_user("Dr A")
    b_user, hb = make_user("Dr B")
    a1, a2 = _two_finals(ha, a_user)
    monkeypatch.setattr(cmp.base, "Groq", lambda api_key: FakeClient([VALID]))
    assert client.post("/api/comparisons", json={"report_ids": [a1["id"], a2["id"]]}, headers=hb).status_code == 404
    other = finalize(ha, make_draft(a_user).id, create_new_anyway=True,
                     new_patient={"full_name": "Someone Else", "gender": "Female"}).json()
    assert client.post("/api/comparisons", json={"report_ids": [a1["id"], other["id"]]},
                       headers=ha).status_code == 422
