"""Phase 6: format registry, selection order, tables, and no flags in exports."""
import docx
import pdfplumber
import pytest

import main
import model.model as m
from model import formats as f
from model.report_export import ExportDocument, build_docx, build_pdf
from tests.fixtures import VALID_GENERATION
from tests.helpers import client, finalize, make_draft, make_user

TABLE = "CAROTID\nFindings\n| Vessel | Finding | Measurement |\n|---|---|---|\n| **ICA** | Patent | 120 cm/s |\n| CCA | Patent | |\nImpression\n1. Normal."


def test_five_presets_with_exact_ids():
    assert [p.id for p in f.PRESETS] == ["classic", "structured", "numbered", "key_findings_first", "measurement_table"]


def test_custom_used_alone():
    r = f.resolve_format("  My format ", "classic")
    assert (r.text, r.format_id, r.is_custom) == ("My format", None, True)


def test_preset_then_default():
    assert f.resolve_format(None, "numbered").format_id == "numbered"
    assert f.resolve_format("", None).format_id == "structured"
    assert f.resolve_format("", "nonsense").format_id == "structured"


def test_organwise_alias():
    assert f.get_preset("organwise").id == "structured"


def test_format_is_always_delimited_in_prompt():
    text = m.build_case_prompt("CT brain", f.resolve_format("", None).text)
    assert "REQUESTED REPORT FORMAT:" in text and "<<<FORMAT" in text and "FORMAT>>>" in text


def _capture(monkeypatch):
    seen = {}

    def fake(prompt, report_format=None, check_fields=None):
        seen.update(format=report_format, check_fields=check_fields)
        return m.ReportAlternatives.model_validate(VALID_GENERATION)

    monkeypatch.setattr(main.model, "generate_reports", fake)
    return seen


def test_generation_uses_preset_then_saved_custom(monkeypatch):
    import rate_limit
    seen = _capture(monkeypatch)
    _, h = make_user()
    rate_limit.reset()
    assert client.post("/api/generate-alternatives", json={"prompt": "CT", "format_id": "organwise"}, headers=h).status_code == 200
    assert seen["format"] == f.get_preset("structured").format_text and seen["check_fields"] is True
    assert client.put("/api/users/me/report-format", json={"text": "Mine\nImpression"}, headers=h).status_code == 200
    body = client.post("/api/generate-alternatives", json={"prompt": "CT", "format_id": "classic"}, headers=h).json()
    assert seen["format"] == "Mine\nImpression" and seen["check_fields"] is False and body["report_format"] == "Mine\nImpression"


def test_custom_format_length_cap_and_clearing():
    _, h = make_user()
    assert client.put("/api/users/me/report-format", json={"text": "x" * 2001}, headers=h).status_code == 422
    client.put("/api/users/me/report-format", json={"text": "Mine"}, headers=h)
    client.put("/api/users/me/report-format", json={"text": " "}, headers=h)
    assert client.get("/api/report-formats", headers=h).json()["custom"] == ""


def test_pdf_renders_table(tmp_path):
    path = build_pdf(ExportDocument("CAROTID", TABLE, f.get_preset("measurement_table").format_text), str(tmp_path / "t.pdf"))
    with pdfplumber.open(path) as pdf:
        text = pdf.pages[0].extract_text()
        assert pdf.pages[0].find_tables() or "ICA Patent 120 cm/s" in text
    assert "|" not in text and "**" not in text


def test_docx_renders_table(tmp_path):
    path = build_docx(ExportDocument("CAROTID", TABLE, f.get_preset("measurement_table").format_text), str(tmp_path / "t.docx"))
    table = docx.Document(path).tables[0]
    assert [c.text for c in table.rows[1].cells] == ["ICA", "Patent", "120 cm/s"]
    assert table.rows[2].cells[2].text == ""


@pytest.mark.parametrize("kind", ["pdf", "docx"])
def test_final_exports_contain_no_flag_text(kind, tmp_path):
    from tests.test_flags import add_flags
    user, h = make_user()
    draft = make_draft(user)
    fid = add_flags(draft, "SECRETFLAGTEXT unclear")[0]
    client.post(f"/api/reports/{draft.id}/flags/{fid}/review", json={"status": "confirmed"}, headers=h)
    final = finalize(h, draft.id).json()
    r = client.get(f"/api/final-reports/{final['id']}/export?format={kind}", headers=h)
    assert r.status_code == 200
    out = tmp_path / f"f.{kind}"
    out.write_bytes(r.content)
    if kind == "pdf":
        with pdfplumber.open(out) as pdf:
            text = " ".join(p.extract_text() or "" for p in pdf.pages)
    else:
        text = " ".join(p.text for p in docx.Document(out).paragraphs)
    assert text and "SECRETFLAGTEXT" not in text
