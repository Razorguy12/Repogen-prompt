"""v2 engine: strict output, retries, truncation handling and rollback."""
import json
from types import SimpleNamespace as NS

import pytest

import model.model as m
from model import prompt_builder as pb


def good():
    return json.dumps({
        "exam": {"modality": "CT", "region": "Brain", "laterality": "Not applicable"},
        "reports": [{"type": t, "word_limit": "1-2", "title": "T", "clinical_details": "", "protocol": "",
                     "observations": "O", "impression": "I", "full_report": "O I"}
                    for t in ("concise", "standard", "detailed")],
        "flags": [],
    })


def reply(content, finish="stop"):
    return NS(choices=[NS(finish_reason=finish, message=NS(content=content))])


class Err(Exception):
    def __init__(self, status, headers=None):
        self.status_code = status
        self.response = NS(headers=headers or {})


class Client:
    def __init__(self, *script):
        self.script, self.calls = list(script), []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "case"}]


@pytest.fixture
def sleeps(monkeypatch):
    out = []
    monkeypatch.setattr(m.time, "sleep", out.append)
    return out


def test_request_uses_new_settings_and_strict_schema():
    c = Client(reply(good()))
    m.generate_v2(c, MSGS)
    kw = c.calls[0]
    assert kw["model"] == "openai/gpt-oss-120b" and kw["temperature"] == 0.15
    assert kw["max_completion_tokens"] == 6000 and kw["reasoning_effort"] == "medium" and kw["timeout"] == 60
    assert kw["response_format"]["json_schema"]["strict"] is True


def test_429_honours_retry_after(sleeps):
    c = Client(Err(429, {"retry-after": "7"}), reply(good()))
    m.generate_v2(c, MSGS)
    assert sleeps == [7.0]


def test_5xx_gives_up_after_three_attempts(sleeps):
    c = Client(Err(503), Err(503), Err(503))
    with pytest.raises(m.ProviderBusyError):
        m.generate_v2(c, MSGS)
    assert len(c.calls) == 3 and len(sleeps) == 2


def test_length_retries_with_double_tokens():
    c = Client(reply('{"partial', "length"), reply(good()))
    m.generate_v2(c, MSGS)
    assert c.calls[1]["max_completion_tokens"] == 12000


def test_length_twice_fails():
    c = Client(reply("x", "length"), reply("x", "length"))
    with pytest.raises(m.GenerationError):
        m.generate_v2(c, MSGS)


def test_corrective_retry_appends_errors_then_fails_cleanly():
    c = Client(reply("not json"), reply("still not"))
    with pytest.raises(m.GenerationError):
        m.generate_v2(c, MSGS)
    assert "failed validation" in c.calls[1]["messages"][-1]["content"]


def test_legacy_restores_prompt_and_version(monkeypatch):
    monkeypatch.setenv("REPORT_ENGINE", "legacy")
    assert "7.17 OTHER" in pb.full_prompt()
    assert m.current_prompt_version().startswith("v2")


def test_comparison_settings_are_unchanged():
    c = Client(reply("{}"))
    m._chat_completion(c, MSGS)
    assert c.calls[0]["model"] == m.GROQ_MODEL and c.calls[0]["temperature"] == 0.2
    assert c.calls[0]["response_format"] == {"type": "json_object"}


def test_413_reports_provider_limit_without_retrying(sleeps):
    c = Client(Err(413))
    with pytest.raises(m.ProviderBusyError):
        m.generate_v2(c, MSGS)
    assert len(c.calls) == 1 and sleeps == []
