"""Split a report's full_report text into a title and headed sections.

full_report is the source of truth (it carries the doctor's edits). The
model writes headings in several styles, and all of them must render the
same way on screen, in PDF and in Word:

    ## CT BRAIN PLAIN            Markdown heading
    **Clinical Details:**        bold label (text may follow on the line)
    Clinical Details             plain line from a custom house format
    Findings: The liver ...      known label followed by text

Mirrored in web/src/lib/reportSections.ts; both are tested against
tests/report_sections_cases.json. Keep them in step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KNOWN_HEADINGS = {
    "clinical details", "clinical detail", "clinical history", "clinical indication", "clinical information",
    "clinical data", "indication", "indications", "history", "clinical profile",
    "protocol", "technique", "procedure", "examination", "study", "exam", "comparison",
    "observations", "observation", "findings", "finding", "report",
    "impression", "impressions", "conclusion", "conclusions", "opinion", "summary",
    "recommendation", "recommendations", "advice", "suggestion", "note", "notes",
}
IMPRESSION_HEADINGS = ("impression", "conclusion", "opinion")
MAX_HEADING_LEN = 60


@dataclass
class Section:
    heading: str | None
    lines: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n".join(self.lines).strip("\n")

    @property
    def is_impression(self) -> bool:
        return bool(self.heading) and any(w in self.heading.lower() for w in IMPRESSION_HEADINGS)


@dataclass
class ParsedReport:
    title: str | None
    sections: list[Section]


def _key(text: str) -> str:
    """Comparison key: lowercase, no markdown, no parentheticals, no trailing colon."""
    text = re.sub(r"[*_#`]", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.strip().rstrip(":").strip()
    return re.sub(r"\s+", " ", text).lower()


def format_headings(report_format: str | None) -> set[str]:
    """Heading names from a custom house format ("Title\\nFindings (by level)\\n...")."""
    names: set[str] = set()
    for line in (report_format or "").splitlines():
        for part in re.split(r"[,:;/]", line):
            key = _key(part)
            if key and len(key) <= MAX_HEADING_LEN and key not in {"title", "organ-wise", "organ wise"}:
                names.add(key)
    return names


def _clean_heading(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_#`]", "", text)).strip().rstrip(":").strip()


def _match_heading(line: str, extra: set[str]) -> tuple[str, str] | None:
    """Return (heading, trailing_text) if the line is a heading, else None."""
    stripped = line.strip()
    if not stripped:
        return None
    m = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", stripped)
    if m:
        return _clean_heading(m.group(1)), ""
    # **Label:** rest   |   **Label**: rest   |   **Label** (alone)
    m = re.match(r"^\*\*([^*]+?)\*\*\s*(:?)\s*(.*)$", stripped)
    if m:
        label, colon, rest = m.group(1), m.group(2), m.group(3)
        if label.rstrip().endswith(":") or colon or not rest:
            if len(_clean_heading(label)) <= MAX_HEADING_LEN:
                return _clean_heading(label), rest.strip()
    names = KNOWN_HEADINGS | extra
    # Plain heading line, optionally ending with a colon.
    if len(stripped) <= MAX_HEADING_LEN and _key(stripped) in names:
        return _clean_heading(stripped), ""
    # "Label: text" where Label is a known heading.
    m = re.match(r"^([A-Za-z][A-Za-z /&()-]{1,40}):\s+(.+)$", stripped)
    if m and _key(m.group(1)) in names:
        return _clean_heading(m.group(1)), m.group(2).strip()
    return None


def parse_report(full_report: str, title: str | None = None, report_format: str | None = None) -> ParsedReport:
    extra = format_headings(report_format)
    title_key = _key(title) if title else None
    sections: list[Section] = []
    current = Section(heading=None)
    parsed_title: str | None = None
    seen_content = False

    for raw in (full_report or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        hit = _match_heading(line, extra)
        # Title: a leading heading (or first line) that matches the report title,
        # or a leading top-level Markdown heading.
        if not seen_content and parsed_title is None and line.strip():
            is_top_md = bool(re.match(r"^#{1,2}\s", line.strip()))
            candidate = hit[0] if hit else _clean_heading(line)
            if (title_key and _key(candidate) == title_key) or (is_top_md and not (hit and _key(hit[0]) in KNOWN_HEADINGS)):
                parsed_title = candidate
                continue
        if hit:
            if current.heading is not None or current.body.strip():
                sections.append(current)
            current = Section(heading=hit[0], lines=[hit[1]] if hit[1] else [])
            seen_content = True
            continue
        if line.strip():
            seen_content = True
        current.lines.append(line)

    if current.heading is not None or current.body.strip():
        sections.append(current)
    for s in sections:  # trim blank edges
        while s.lines and not s.lines[0].strip():
            s.lines.pop(0)
        while s.lines and not s.lines[-1].strip():
            s.lines.pop()
    return ParsedReport(title=parsed_title or title, sections=sections)


def body_word_count(full_report: str, title: str | None = None, report_format: str | None = None) -> int:
    """Words in section bodies only (title and headings excluded), as the prompt counts."""
    parsed = parse_report(full_report, title, report_format)
    text = " ".join(s.body for s in parsed.sections)
    text = re.sub(r"[*_`>#]", " ", text)
    return len([w for w in text.split() if re.search(r"[^\W_]", w)])
