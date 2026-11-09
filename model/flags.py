"""Turn model flag strings and server warnings into structured review records."""
from __future__ import annotations

import re

_PREFIXES = (
    ("Assumed absent alongside a reported abnormality:", "assumed_absent", "high", True),
    ("Assumed normal because not mentioned:", "assumed_normal", "medium", True),
    ("Not commented upon:", "anomaly_unmentioned", "high", True),
    ("No findings supplied", "no_findings", "high", True),
    ("Fetal sex omitted.", "fetal_sex_omitted", "info", False),
)
SPLIT_TYPES = {"assumed_absent", "assumed_normal"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}
_MAX_ITEM_WORDS = 12


def split_items(body: str) -> list[str]:
    """Split on commas and semicolons; an odd result falls back to one item."""
    body = body.strip().rstrip(".").strip()
    parts = [p.strip() for p in re.split(r"[,;]", body)]
    if not all(len(p) >= 2 and len(p.split()) <= _MAX_ITEM_WORDS for p in parts):
        return [body]
    return parts


def _record(raw: str, type_: str, severity: str, requires: bool, source: str, body: str | None = None) -> dict:
    texts = split_items(body) if type_ in SPLIT_TYPES and body is not None and body.strip() else [raw]
    return {
        "type": type_, "severity": severity, "raw_text": raw, "source": source, "requires_review": requires,
        "status": "open", "items": [{"text": t, "status": "open"} for t in texts],
    }


def parse_flag(raw: str) -> dict:
    for prefix, type_, severity, requires in _PREFIXES:
        if raw.startswith(prefix):
            return _record(raw, type_, severity, requires, "model", raw[len(prefix):])
    return _record(raw, "other", "high", True, "model")


def build_flag_records(model_flags: list[str], warnings: list[str]) -> list[dict]:
    records = [parse_flag(f) for f in model_flags]
    records += [_record(w, "validation", "high", True, "server") for w in warnings]
    return records


def rollup_status(items: list[dict]) -> str:
    statuses = {i["status"] for i in items}
    if "open" in statuses:
        return "open"
    if "corrected" in statuses:
        return "corrected"
    if statuses == {"not_applicable"}:
        return "not_applicable"
    return "confirmed"
