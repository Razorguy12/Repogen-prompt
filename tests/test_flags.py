"""Phase 4: flag parsing, storage and review permissions."""
import pytest

from database import ReportFlag, SessionLocal
from model.flags import build_flag_records, parse_flag, rollup_status, split_items
from tests.helpers import client, make_draft, make_user


@pytest.mark.parametrize("raw,type_,severity,requires", [
    ("Assumed absent alongside a reported abnormality: no midline shift, no herniation", "assumed_absent", "high", True),
    ("Assumed normal because not mentioned: liver; spleen", "assumed_normal", "medium", True),
    ("Not commented upon: heart, limbs", "anomaly_unmentioned", "high", True),
    ("No findings supplied; reported as normal.", "no_findings", "high", True),
    ("Fetal sex omitted.", "fetal_sex_omitted", "info", False),
    ("XYZ is an unclear abbreviation", "other", "high", True),
])
def test_prefixes(raw, type_, severity, requires):
    r = parse_flag(raw)
    assert (r["type"], r["severity"], r["requires_review"], r["raw_text"]) == (type_, severity, requires, raw)


def test_items_split_on_commas_and_semicolons():
    assert [i["text"] for i in parse_flag("Assumed normal because not mentioned: liver, spleen; kidneys.")["items"]] == [
        "liver", "spleen", "kidneys"]


def test_odd_split_falls_back_to_single_item():
    assert split_items("liver,, spleen") == ["liver,, spleen"]


def test_only_listed_types_split():
    assert len(parse_flag("Not commented upon: heart, limbs")["items"]) == 1


def test_server_warnings_are_validation_flags():
    r = build_flag_records([], ["Standard report: measurement not in the dictation: 2 mm."])[0]
    assert r["type"] == "validation" and r["source"] == "server" and r["requires_review"]


def test_rollup():
    assert rollup_status([{"status": "confirmed"}, {"status": "open"}]) == "open"
    assert rollup_status([{"status": "confirmed"}, {"status": "corrected"}]) == "corrected"


def add_flags(draft, *raw):
    db = SessionLocal()
    for record in build_flag_records(list(raw), []):
        db.add(ReportFlag(draft_id=draft.id, **record))
    db.commit()
    rows = [r.id for r in db.query(ReportFlag).filter_by(draft_id=draft.id).order_by(ReportFlag.id)]
    db.close()
    return rows


def test_item_review_records_reviewer_after_last_item():
    user, h = make_user()
    draft = make_draft(user)
    fid = add_flags(draft, "Assumed absent alongside a reported abnormality: no shift, no herniation")[0]
    url = f"/api/reports/{draft.id}/flags/{fid}/review"
    assert client.post(url, json={"status": "confirmed", "item_index": 0}, headers=h).json()["status"] == "open"
    body = client.post(url, json={"status": "corrected", "item_index": 1}, headers=h).json()
    assert body["status"] == "corrected" and body["reviewed_by"] == user.id


def test_another_user_cannot_review():
    user, _ = make_user()
    _, other = make_user()
    draft = make_draft(user)
    fid = add_flags(draft, "Unclear term")[0]
    assert client.post(f"/api/reports/{draft.id}/flags/{fid}/review", json={"status": "confirmed"}, headers=other).status_code == 404
    assert client.get(f"/api/reports/{draft.id}/flags", headers=other).status_code == 404


def test_info_flag_cannot_be_reviewed_and_order_is_by_severity():
    user, h = make_user()
    draft = make_draft(user)
    ids = add_flags(draft, "Fetal sex omitted.", "Assumed normal because not mentioned: liver", "Unclear term")
    assert client.post(f"/api/reports/{draft.id}/flags/{ids[0]}/review", json={"status": "confirmed"}, headers=h).status_code == 409
    assert [f["severity"] for f in client.get(f"/api/reports/{draft.id}/flags", headers=h).json()] == ["high", "medium", "info"]


# Phase 5: finalise gate
from tests.helpers import finalize  # noqa: E402


def test_open_flag_blocks_finalize_with_outstanding_items():
    user, h = make_user()
    draft = make_draft(user)
    add_flags(draft, "Unclear term")
    r = finalize(h, draft.id)
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["code"] == "flags_outstanding" and d["outstanding"][0]["raw_text"] == "Unclear term"


def test_reviewed_flags_pass_and_info_flag_does_not_block():
    user, h = make_user()
    draft = make_draft(user)
    fid = add_flags(draft, "Unclear term", "Fetal sex omitted.")[0]
    client.post(f"/api/reports/{draft.id}/flags/{fid}/review", json={"status": "not_applicable"}, headers=h)
    r = finalize(h, draft.id)
    assert r.status_code == 200, r.text
    assert "Unclear term" in r.json()["flags"]


def test_pre_release_draft_without_records_still_finalizes():
    user, h = make_user()
    assert finalize(h, make_draft(user).id).status_code == 200


def test_confirm_all_does_not_overwrite_a_corrected_item():
    user, h = make_user()
    draft = make_draft(user)
    fid = add_flags(draft, "Assumed normal because not mentioned: liver, spleen")[0]
    url = f"/api/reports/{draft.id}/flags/{fid}/review"
    client.post(url, json={"status": "corrected", "item_index": 0}, headers=h)
    body = client.post(url, json={"status": "confirmed"}, headers=h).json()
    assert [i["status"] for i in body["items"]] == ["corrected", "confirmed"] and body["status"] == "corrected"


def test_no_review_after_finalize():
    user, h = make_user()
    draft = make_draft(user)
    fid = add_flags(draft, "Fetal sex omitted.", "Unclear")[1]
    url = f"/api/reports/{draft.id}/flags/{fid}/review"
    client.post(url, json={"status": "confirmed"}, headers=h)
    finalize(h, draft.id)
    assert client.post(url, json={"status": "open"}, headers=h).status_code == 409
