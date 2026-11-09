"""Server-side checks on every v2 model response, run before anything is saved.

Hard failures raise OutputValidationError and trigger one corrective retry.
Warnings do not block; each becomes a server-generated review flag. Messages
name the problem only and must never be logged with findings or report text.
"""
from __future__ import annotations

import re

from model.report_sections import body_word_count

ASSUMED_NORMAL_PREFIX = "Assumed normal because not mentioned:"
TEXT_FIELDS = ("title", "clinical_details", "protocol", "observations", "impression", "full_report")
REQUIRED_FIELDS = ("word_limit", *TEXT_FIELDS)

_OBSTETRIC = re.compile(
    r"obstet|f(o)?etus|f(o)?etal|gestation|pregnan|antenatal|anomaly scan|growth scan|\bnt scan\b|\btiffa\b|\biup\b",
    re.I)
_ANOMALY = re.compile(r"anomaly scan|\btiffa\b|level[- ]?(ii|2)\b(?=.*(scan|f(o)?etal|obstet|anomaly))|\btargeted scan\b",
                      re.I | re.S)
_FETAL_SEX = re.compile(
    r"\b(male|female)\s+(f(o)?etus|baby|child|infant|sex|gender)\b|\bbaby\s+(boy|girl)\b|"
    r"\bf(o)?etal\s+(sex|gender)\b|\b(sex|gender)\s+of\s+the\s+(f(o)?etus|baby)\b|"
    r"\bexternal\s+genitalia\b|\bgenital\s+tubercle\b|\b(penis|scrotum|scrotal|labia|labial)\b",
    re.I)

_NORMAL_WORDS = re.compile(r"\b(normal|unremarkable|no\s+\w+|intact|preserved|patent)\b", re.I)
_STOP = {"appears", "appear", "normal", "unremarkable", "this", "examination", "with", "without", "that", "there",
         "seen", "noted", "intact", "preserved", "patent", "study", "visualised", "visualized", "both", "and", "are",
         "abnormality", "evidence", "remaining", "otherwise", "limits", "within"}

_NUM = r"\d+(?:\.\d+)?"
_MEASURE = re.compile(rf"(?<![A-Za-z\d.\-])({_NUM})\s*(?:cm/s|mm|cm|ml|hu|bpm|weeks?|wks?|g\b|%)(?![A-Za-z])", re.I)
_DIMENSION = re.compile(rf"(?<![A-Za-z\d.\-])({_NUM}(?:\s*[x×]\s*{_NUM})+)", re.I)
_ANY_NUMBER = re.compile(_NUM)
_CLASSIFICATIONS = {
    "BI-RADS": r"bi[-\s]?rads", "TIRADS": r"ti[-\s]?rads", "O-RADS": r"o[-\s]?rads",
    "Kellgren": r"kellgren", "NASCET": r"nascet", "Papile": r"papile",
}
_RANGE = re.compile(r"(\d+)\s*[-–—]\s*(\d+)|(\d+)\s+to\s+(\d+)")


class OutputValidationError(ValueError):
    """The response breaks a hard rule. str(exc) lists fixes for the corrective retry."""


def _report_text(report) -> str:
    return "\n".join(getattr(report, f) or "" for f in TEXT_FIELDS)


def _normalise(text: str) -> str:
    text = re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", " ", text or "")
    text = re.sub(r"[*_`#>|]", " ", text)
    return " ".join(text.lower().split())


def _is_obstetric(result, findings: str) -> bool:
    return bool(_OBSTETRIC.search(findings)) or bool(_OBSTETRIC.search(result.exam.region))


def _has_unsupplied_normal(report, findings: str) -> bool:
    """True if a normal statement names a structure the radiologist did not dictate."""
    source = findings.lower()
    for sentence in re.split(r"(?<=[.;])\s+|\n+", report.observations or ""):
        if not _NORMAL_WORDS.search(sentence):
            continue
        words = [w for w in re.findall(r"[a-z]{4,}", sentence.lower()) if w not in _STOP]
        if any(w not in source for w in words):
            return True
    return False


def hard_failures(result, findings: str) -> list[str]:
    errors: list[str] = []
    for report in result.reports:
        for name in REQUIRED_FIELDS:
            if not (getattr(report, name) or "").strip():
                errors.append(f'The {report.type} report has an empty "{name}" field.')
    if _is_obstetric(result, findings) and any(_FETAL_SEX.search(_report_text(r)) for r in result.reports):
        errors.append("A report states or implies fetal sex. Remove it from every report (PC-PNDT Act).")
    anomaly = bool(_ANOMALY.search(findings)) or bool(_ANOMALY.search(result.reports[0].title or ""))
    has_flag = any(f.startswith(ASSUMED_NORMAL_PREFIX) for f in result.flags)
    if not anomaly and not has_flag and any(_has_unsupplied_normal(r, findings) for r in result.reports):
        errors.append(f'Add the mandatory flag beginning "{ASSUMED_NORMAL_PREFIX}" listing the assumed structures.')
    return errors


def _source_numbers(findings: str) -> set[float]:
    return {float(n) for n in _ANY_NUMBER.findall(findings)}


def _unsupplied_measurements(text: str, supplied: set[float]) -> list[str]:
    found: list[str] = []
    for match in _DIMENSION.finditer(text):
        if any(float(n) not in supplied for n in _ANY_NUMBER.findall(match.group(1))):
            found.append(match.group(1))
    stripped = _DIMENSION.sub(" ", text)
    for match in _MEASURE.finditer(stripped):
        if float(match.group(1)) not in supplied:
            found.append(match.group(0).strip())
    return list(dict.fromkeys(found))


def _opposite_side(findings: str, exam_laterality: str) -> str | None:
    """The side that should not appear, for a unilateral study with one side dictated.

    Limited to unilateral exams: on chest or abdomen studies a finding on one side
    legitimately sits beside a normal statement about the other.
    """
    if exam_laterality not in ("Left", "Right"):
        return None
    left, right = bool(re.search(r"\bleft\b", findings, re.I)), bool(re.search(r"\bright\b", findings, re.I))
    if left == right:
        return None
    return "right" if left else "left"


def warnings(result, findings: str, report_format: str | None = None) -> list[str]:
    out: list[str] = []
    supplied = _source_numbers(findings)
    wrong_side = _opposite_side(findings, result.exam.laterality)
    for report in result.reports:
        label = report.type.title()
        text = _report_text(report)
        for item in _unsupplied_measurements(text, supplied):
            out.append(f"{label} report: measurement not in the dictation: {item}.")
        for name, pattern in _CLASSIFICATIONS.items():
            if re.search(pattern, text, re.I) and not re.search(pattern, findings, re.I):
                out.append(f"{label} report: classification not in the dictation: {name}.")
        limits = _RANGE.search(report.word_limit or "")
        if limits:
            low, high = (int(g) for g in limits.groups() if g)
            count = body_word_count(report.full_report, report.title, report_format)
            if not low <= count <= high:
                out.append(f"{label} report: {count} words, outside the {low}-{high} range.")
        if wrong_side and re.search(rf"\b{wrong_side}\b", text, re.I):
            out.append(f"{label} report: mentions the {wrong_side} side, but the dictation gives only the other side.")
        if not (report_format or "").strip():
            whole = _normalise(report.full_report)
            for name in ("observations", "impression"):
                if _normalise(getattr(report, name)) not in whole:
                    out.append(f"{label} report: full report does not match the {name} section.")
    return out


def validate_output(result, findings: str, report_format: str | None = None) -> list[str]:
    """Raise OutputValidationError on a hard failure; otherwise return warning texts."""
    errors = hard_failures(result, findings)
    if errors:
        raise OutputValidationError("\n".join(errors))
    return warnings(result, findings, report_format)
