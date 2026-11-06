import json

import pytest

import model.model as m
from tests.fixtures import FakeClient, generation, variant


def test_valid_response_parses():
    result = m.parse_generation(json.dumps(generation(flags=["Fetal sex omitted"])))
    assert result.exam.modality == "XR"
    assert [r.type for r in result.reports] == ["concise", "standard", "detailed"]
    assert result.flags == ["Fetal sex omitted"]


def test_fenced_json_is_accepted():
    result = m.parse_generation("```json\n" + json.dumps(generation()) + "\n```")
    assert result.exam.region == "Chest"


def test_variable_word_limit_passes_through():
    data = generation()
    data["reports"][2]["word_limit"] = "300-450"
    assert m.parse_generation(json.dumps(data)).reports[2].word_limit == "300-450"


@pytest.mark.parametrize("bad", [
    "not json",
    json.dumps({"reports": generation()["reports"], "flags": []}),           # missing exam
    json.dumps(generation(flags=None)),                                       # flags not a list
    json.dumps(generation(exam={"modality": "PET-CT", "region": "Chest", "laterality": "Left"})),
    json.dumps(generation(reports=[variant("standard", "1"), variant("concise", "1"), variant("detailed", "1")])),
    json.dumps(generation(reports=generation()["reports"][:2])),
])
def test_invalid_responses_rejected(bad):
    with pytest.raises(ValueError):
        m.parse_generation(bad)


def test_modality_synonyms_normalised():
    data = generation(exam={"modality": "usg", "region": "KUB", "laterality": "bilateral"})
    exam = m.parse_generation(json.dumps(data)).exam
    assert (exam.modality, exam.laterality) == ("US", "Bilateral")


def test_malformed_then_valid_retries_exactly_once():
    client = FakeClient(["{oops", generation()])
    result, attempts = m.generate_validated(client, [{"role": "user", "content": "x"}], m.parse_generation)
    assert attempts == 2 and result.exam.modality == "XR"
    assert len(client.completions.calls) == 2
    retry_msgs = client.completions.calls[1]["messages"]
    assert retry_msgs[-1]["content"] == m.SCHEMA_RETRY_INSTRUCTION


def test_malformed_twice_raises_generation_error():
    client = FakeClient(["{oops", "still not json"])
    with pytest.raises(m.GenerationError):
        m.generate_validated(client, [{"role": "user", "content": "x"}], m.parse_generation)
    assert len(client.completions.calls) == 2


def test_old_draft_payload_has_safe_defaults():
    import main
    from database import Report

    legacy = Report(id=1, user_id=1, status="draft", input_params=json.dumps({
        "kind": "prompt", "prompt": "cxr", "selected": "standard",
        "alternatives": generation()["reports"],
    }))
    payload = main.session_payload(legacy)
    assert payload["flags"] == [] and payload["exam"] is None
    main.PromptSessionResponse(**{**payload, "created_at": "2026-01-01T00:00:00Z"})
