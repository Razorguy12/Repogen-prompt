"""The trimmed prompt must keep every rule and every entry that could apply."""
import re

import pytest

import model.prompt_builder as b

FULL = b.full_prompt()


def _section(text, number):
    for num, header, body in b._sections(text):
        if num == number:
            return header + body
    raise KeyError(number)


def _numbers():
    return [n for n, _, _ in b._sections(FULL) if n]


def _glossary_entries():
    body = _section(FULL, "0")
    g = re.search(r"^RADIOLOGY GLOSSARY \(", body, re.M).start()
    a = re.search(r"^AMBIGUOUS ABBREVIATIONS \(", body, re.M).start()
    entries = [ln for ln in body[g:a].split("\n") if ln.startswith("  ") and not ln.startswith("    ")]
    entries += [ln for ln in body[a:].split("\n") if ln.startswith("  ")]
    return entries


CASES = [
    "xray - Right lower zone opacity, BVM prominence, Left peri-hilar infiltrates",
    "CT brain plain. Extra-axial lesion. Headache 2 weeks.",
    "USG obstetric: SLIUF, FHR 148, BPD 48 mm. Male fetus.",
    "Carotid doppler: ICA PSV 120 cm/s",
    "Brain: 2 cm lesion",
]


@pytest.mark.parametrize("findings", CASES)
def test_all_sections_except_0_and_7_are_verbatim(findings):
    trimmed = b.build_system_prompt(findings)
    for number in _numbers():
        if number not in {"0", "7"}:
            assert _section(FULL, number).strip() in trimmed, number


@pytest.mark.parametrize("findings", CASES)
def test_rules_0_1_to_0_6_are_always_kept(findings):
    body = _section(FULL, "0")
    rules = body[:re.search(r"^RADIOLOGY GLOSSARY \(", body, re.M).start()]
    assert rules.strip() in b.build_system_prompt(findings)


@pytest.mark.parametrize("entry", _glossary_entries())
def test_each_glossary_entry_is_included_when_its_abbreviation_appears(entry):
    for term in b._entry_terms(entry):
        trimmed = b.build_system_prompt(f"Findings: {term} noted.")
        assert entry.strip() in trimmed, (term, entry)


def test_unrelated_glossary_entries_are_dropped():
    trimmed = b.build_system_prompt("xray - BVM prominence")
    assert "bronchovascular markings" in trimmed
    assert "nuchal translucency" not in trimmed and "saphenofemoral" not in trimmed


def test_fetal_sex_rule_present_for_obstetric_input():
    trimmed = b.build_system_prompt("USG: single live fetus, cardiac activity present, male")
    assert "NEVER state, imply, or hint at fetal sex" in trimmed


def test_section_7_is_sent_whole_for_a_recognised_exam():
    # The all-modality prompt has no numbered 7.x sub-sections to select from.
    assert _section(FULL, "7").strip() in b.build_system_prompt("CT brain plain. Headache 2 weeks.")


def test_anomaly_and_fetal_sex_flags_use_fixed_prefixes():
    assert 'beginning "Not commented upon:"' in " ".join(FULL.split())
    assert 'add the flag "Fetal sex omitted."' in " ".join(FULL.split())


def test_unknown_exam_keeps_every_template():
    assert _section(FULL, "7").strip() in b.build_system_prompt("Brain: 2 cm lesion")


def test_trimming_can_be_disabled(monkeypatch):
    monkeypatch.setenv("REPORT_PROMPT_TRIM", "0")
    assert b.build_system_prompt("xray - BVM") == FULL


def test_trimmed_is_smaller():
    assert len(b.build_system_prompt(CASES[0])) < len(FULL)
