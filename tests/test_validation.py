"""Phase 3: hard failures and warnings on model output."""
import pytest

import model.model as m
from model.validation import OutputValidationError, validate_output, warnings

FLAG = "Assumed normal because not mentioned: spleen"
WORDS = " ".join(["word"] * 20)


def build(obs="Liver shows a lesion.", imp="Liver lesion.", flags=(FLAG,), modality="CT", region="Abdomen",
          laterality="Not applicable", extra=""):
    full = f"TITLE\nObservations\n{obs} {extra} {WORDS}\nImpression\n{imp}"
    return m.ReportAlternatives.model_validate({
        "exam": {"modality": modality, "region": region, "laterality": laterality},
        "reports": [{"type": t, "word_limit": "1-500", "title": "CT", "clinical_details": "Not provided",
                     "protocol": "Not provided", "observations": f"{obs} {extra} {WORDS}".strip(), "impression": imp,
                     "full_report": full} for t in ("concise", "standard", "detailed")],
        "flags": list(flags),
    })


def test_clean_output_has_no_warnings():
    assert validate_output(build(), "CT abdomen liver lesion") == []


def test_empty_required_field_fails():
    r = build()
    r.reports[1].impression = "  "
    with pytest.raises(OutputValidationError, match="impression"):
        validate_output(r, "CT abdomen liver lesion")


def test_missing_assumed_normal_flag_fails():
    with pytest.raises(OutputValidationError, match="Assumed normal"):
        validate_output(build(obs="The spleen is normal.", flags=()), "CT abdomen liver lesion")


def test_fully_supplied_study_needs_no_assumed_flag():
    validate_output(build(obs="The spleen is normal.", flags=()), "CT abdomen spleen normal")


def test_anomaly_scan_skips_assumed_flag():
    validate_output(build(obs="The spine appears normal.", flags=(), region="Obstetric"), "Anomaly scan, heart normal")


@pytest.mark.parametrize("phrase", ["Male fetus seen.", "baby girl", "Fetal sex not stated", "external genitalia normal"])
def test_fetal_sex_fails_on_obstetric(phrase):
    with pytest.raises(OutputValidationError, match="fetal sex"):
        validate_output(build(extra=phrase, region="Obstetric"), "Growth scan BPD 80 mm")


def test_female_patient_is_not_fetal_sex():
    validate_output(build(extra="Female patient.", region="Obstetric"), "Growth scan")


def test_scrotum_allowed_outside_obstetrics():
    validate_output(build(extra="Scrotum shown.", region="Scrotum"), "USG scrotum")


def text_warnings(extra, source="CT liver", **kw):
    return warnings(build(extra=extra, **kw), source)


def test_unsupplied_measurement_warns():
    assert any("12 mm" in w for w in text_warnings("Lesion 12 mm."))


def test_supplied_measurement_and_dimension_pass():
    assert text_warnings("Lesion 3.4 x 2.3 cm.", "CT liver 3.4 x 2.3 cm") == []


def test_unsupplied_dimension_warns():
    assert any("2 x 3" in w for w in text_warnings("Lesion 2 x 3 cm."))


def test_labels_and_list_numbers_are_ignored():
    assert text_warnings("1. L4-L5 disc. C5 and T2 and S1 Level II.") == []


def test_classification_warns_only_when_unsupplied():
    assert any("BI-RADS" in w for w in text_warnings("BIRADS 4."))
    assert text_warnings("BI-RADS 4.", "Mammography BI RADS 4") == []


def test_word_count_warns():
    r = build()
    for rep in r.reports:
        rep.word_limit = "300-420"
    assert sum("outside" in w for w in warnings(r, "CT liver")) == 3


def test_laterality_mismatch_on_unilateral_exam():
    out = text_warnings("Left shoulder noted.", "MRI right shoulder", laterality="Right")
    assert sum("left side" in w for w in out) == 3


def test_opposite_side_allowed_on_non_lateral_exam():
    assert text_warnings("Left lung clear.", "CXR right lower zone opacity") == []


def test_field_mismatch_warns_only_without_custom_format():
    r = build()
    for rep in r.reports:
        rep.impression = "Something else entirely."
    assert any("does not match" in w for w in warnings(r, "CT liver"))
    assert not any("does not match" in w for w in warnings(r, "CT liver", "Custom\nImpression"))


def test_hard_failure_triggers_corrective_retry_and_saves_nothing():
    from tests.test_llm_v2 import MSGS, Client, good, reply
    calls = []

    def bad(result):
        calls.append(1)
        raise OutputValidationError("A report states or implies fetal sex.")

    c = Client(reply(good()), reply(good()))
    with pytest.raises(m.GenerationError):
        m.generate_v2(c, MSGS, validator=bad)
    assert len(calls) == 2 and "fetal sex" in c.calls[1]["messages"][-1]["content"]


def test_warnings_cannot_come_from_the_model():
    from tests.test_llm_v2 import MSGS, Client, good, reply
    result = m.generate_v2(Client(reply(good())), MSGS, validator=lambda r: ["server warning"])
    assert result.validation_warnings == ["server warning"]


def test_empty_clinical_details_and_protocol_become_not_provided():
    r = build()
    r.reports[0].clinical_details = ""
    r.reports[2].protocol = "  "
    validate_output(r, "CT abdomen liver lesion")
    assert r.reports[0].clinical_details == "Not provided" and r.reports[2].protocol == "Not provided"
