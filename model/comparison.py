"""Interval comparison of two final reports (prompt: comparison_system_prompt_v1.txt).

Privacy: only report text, exam fields and the interval are sent. Patient
name, ID and gender are never part of the request, and known identifiers
are additionally scrubbed from the report text in case a doctor typed them.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from model import model as base

logger = logging.getLogger("repogen.comparison")

COMPARISON_PROMPT_VERSION = "v1"
COMPARISON_SYSTEM_PROMPT = (Path(__file__).parent / "comparison_system_prompt_v1.txt").read_text(encoding="utf-8").strip()

Category = Literal["NEW", "RESOLVED", "INCREASED", "DECREASED", "STABLE", "NOT COMPARABLE"]
CATEGORY_ORDER = ["NEW", "INCREASED", "DECREASED", "RESOLVED", "STABLE", "NOT COMPARABLE"]


class Change(BaseModel):
    finding: str
    category: Category
    baseline: str
    follow_up: str
    note: str = ""


class ComparisonResult(BaseModel):
    comparison_title: str
    interval_days: int
    examinations_comparable: bool
    summary: str
    changes: list[Change]
    comparison_impression: list[str]
    limitations: list[str]
    flags: list[str]


class ExamSide(BaseModel):
    modality: str
    region: str
    laterality: str
    text: str


def scrub_identifiers(text: str, identifiers: list[str]) -> str:
    """Replace known patient identifiers (full name, name parts, MRN) with [redacted]."""
    terms: set[str] = set()
    for value in identifiers:
        value = (value or "").strip()
        if not value:
            continue
        terms.add(value)
        terms.update(part for part in re.split(r"[\s.,]+", value) if len(part) >= 3)
    for term in sorted(terms, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", "[redacted]", text, flags=re.IGNORECASE)
    return text


def build_user_message(baseline: ExamSide, followup: ExamSide, interval_days: int) -> str:
    def header(label: str, side: ExamSide) -> str:
        return f"{label} (modality: {side.modality}, region: {side.region}, laterality: {side.laterality}):"
    return "\n".join([
        f"INTERVAL_DAYS: {interval_days}",
        header("BASELINE", baseline),
        baseline.text.strip(),
        header("FOLLOW-UP", followup),
        followup.text.strip(),
    ])


def parse_comparison(content: str) -> ComparisonResult:
    try:
        return ComparisonResult.model_validate(base._extract_json(content or ""))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(str(exc)) from exc


def finalize_result(result: ComparisonResult, computed_interval: int) -> tuple[ComparisonResult, bool]:
    """Enforce server-side invariants. Returns (result, interval_was_adjusted)."""
    adjusted = result.interval_days != computed_interval
    if adjusted:
        logger.warning("Comparison interval mismatch: model=%s computed=%s; using computed",
                       result.interval_days, computed_interval)
        result.interval_days = computed_interval
    result.changes.sort(key=lambda c: CATEGORY_ORDER.index(c.category))
    return result, adjusted


def generate_comparison(baseline: ExamSide, followup: ExamSide, interval_days: int, client=None):
    """Returns (ComparisonResult, attempts, interval_adjusted)."""
    if client is None:
        if not base.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")
        client = base.Groq(api_key=base.GROQ_API_KEY)
    messages = [
        {"role": "system", "content": COMPARISON_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(baseline, followup, interval_days)},
    ]
    result, attempts = base.generate_validated(client, messages, parse_comparison)
    result, adjusted = finalize_result(result, interval_days)
    return result, attempts, adjusted
