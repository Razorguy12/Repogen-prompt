import io
import json
from pathlib import Path

import docx
import pdfplumber

import model.model as m
from tests.helpers import client, finalize, make_draft, make_user

CASES = json.loads((Path(__file__).parent / "report_sections_cases.json").read_text())


def _variant(case):
    return m.RadiologyReport(type="standard", word_limit="150-200", title=case["title"], clinical_details="old",
                             protocol="old", observations="old", impression="old", full_report=case["full_report"])


def _docx_paragraphs(path_or_bytes):
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    return [p.text for p in docx.Document(src).paragraphs if p.text.strip()]


def test_docx_uses_full_report_sections_not_stale_fields():
    case = CASES[1]  # plain custom-format headings
    paras = _docx_paragraphs(m.report_to_docx(_variant(case), report_format=case["report_format"]))
    assert paras[0] == "CT BRAIN PLAIN"
    for heading in ("CLINICAL DETAILS", "PROTOCOL", "OBSERVATIONS", "IMPRESSION"):
        assert heading in paras
    assert "Most compatible with a meningioma." in paras
    assert "old" not in paras                                   # stale section fields are not exported
    assert not any("**" in p or p.startswith("#") for p in paras)


def test_pdf_has_headings_and_no_markdown():
    case = CASES[0]
    with pdfplumber.open(m.report_to_pdf(_variant(case))) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "CLINICAL DETAILS" in text and "IMPRESSION" in text and "Likely meningioma." in text
    assert "**" not in text and "##" not in text


def test_final_report_export_pdf_and_docx_scoped():
    user, h = make_user()
    other, ho = make_user()
    fr = finalize(h, make_draft(user, full_report=CASES[0]["full_report"]).id,
                  new_patient={"full_name": "Export Person", "patient_identifier": "EX1", "gender": "Female"}).json()
    r = client.get(f"/api/final-reports/{fr['id']}/export?format=docx", headers=h)
    assert r.status_code == 200
    assert "Export" not in r.headers["content-disposition"]       # no patient name in file name
    paras = _docx_paragraphs(r.content)
    assert "CT BRAIN PLAIN" in paras and "IMPRESSION" in paras
    assert any(p.startswith("Finalized by") for p in paras)
    r = client.get(f"/api/final-reports/{fr['id']}/export?format=pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert client.get(f"/api/final-reports/{fr['id']}/export?format=pdf", headers=ho).status_code == 404
