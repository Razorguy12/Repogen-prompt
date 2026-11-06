import json
from pathlib import Path

import pytest

from model.report_sections import body_word_count, parse_report

CASES = json.loads((Path(__file__).parent / "report_sections_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_parse_matches_shared_fixture(case):
    parsed = parse_report(case["full_report"], case["title"], case["report_format"])
    exp = case["expected"]
    assert parsed.title == exp["title"]
    assert [[s.heading, s.body] for s in parsed.sections] == exp["sections"]
    assert [s.is_impression for s in parsed.sections] == exp["impression"]


def test_word_count_excludes_title_and_headings():
    c = CASES[1]
    assert body_word_count(c["full_report"], c["title"], c["report_format"]) == 4 + 6 + 3 + 5
