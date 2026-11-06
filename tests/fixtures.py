"""Shared sample payloads for tests. All content is synthetic."""
import copy
import json


def variant(type_, word_limit):
    return {
        "type": type_,
        "word_limit": word_limit,
        "title": "CHEST RADIOGRAPH",
        "clinical_details": "Not provided.",
        "protocol": "Chest radiograph.",
        "observations": "Prominent bronchovascular markings. Right lower zone opacity.",
        "impression": "Right lower zone opacity.",
        "full_report": "## CHEST RADIOGRAPH\n\n**Clinical Details:** Not provided.\n\n### IMPRESSION\nRight lower zone opacity.",
    }


VALID_GENERATION = {
    "exam": {"modality": "XR", "region": "Chest", "laterality": "Not applicable"},
    "reports": [variant("concise", "80-120"), variant("standard", "120-180"), variant("detailed", "180-260")],
    "flags": [],
}


def generation(**overrides):
    data = copy.deepcopy(VALID_GENERATION)
    data.update(overrides)
    return data


class FakeCompletions:
    """Mimics groq_client.chat.completions; returns queued outputs in order."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        msg = type("M", (), {"content": text})
        choice = type("C", (), {"message": msg})
        return type("R", (), {"choices": [choice]})


class FakeClient:
    def __init__(self, outputs):
        self.completions = FakeCompletions(outputs)
        self.chat = type("Chat", (), {"completions": self.completions})
