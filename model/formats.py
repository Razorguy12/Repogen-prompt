"""Report format registry and selection order."""
from __future__ import annotations

from dataclasses import asdict, dataclass

CUSTOM_FORMAT_MAX_CHARS = 2000
DEFAULT_FORMAT_ID = "structured"
ALIASES = {"organwise": "structured"}
# Presets whose full_report keeps observations and impression as contiguous text.
FIELD_MATCH_PRESETS = {"classic", "structured", "numbered"}


@dataclass(frozen=True)
class ReportFormat:
    id: str
    label: str
    description: str
    format_text: str


@dataclass(frozen=True)
class ResolvedFormat:
    text: str
    format_id: str | None
    is_custom: bool

    @property
    def check_fields(self) -> bool:
        return not self.is_custom and self.format_id in FIELD_MATCH_PRESETS


PRESETS = (
    ReportFormat("classic", "Classic", "Short flowing paragraphs under the traditional headings.",
                 "Title\nClinical Details (optional)\nProtocol (optional)\n"
                 "Observations: short flowing paragraphs, no bullets\nImpression"),
    ReportFormat("structured", "Structured", "Findings by region with a bullet for each structure.",
                 "Title\nClinical Indication (optional)\nTechnique (optional)\n"
                 "Findings: a heading for each region, one bullet per structure, structure name in bold\n"
                 "Impression: numbered list, abnormal findings only, most significant first"),
    ReportFormat("numbered", "Numbered", "Numbered findings, abnormal first, then a numbered impression.",
                 "Examination\nTechnique (optional)\n"
                 "Findings: numbered list, abnormal findings first, then normal structures in one final item\n"
                 "Impression: numbered list\nRecommendation (optional)"),
    ReportFormat("key_findings_first", "Key findings first", "Opens with the impression and abnormal findings.",
                 "Title\nImpression: numbered list, abnormal findings only, most significant first\n"
                 "Key Findings: abnormal structures only, one bullet each\n"
                 "Remainder of the Study: normal structures in one short paragraph\nTechnique (optional)"),
    ReportFormat("measurement_table", "Measurement table", "Findings in a table of structures and measurements.",
                 "Title\nClinical Indication (optional)\nTechnique (optional)\n"
                 "Findings: table with columns Structure or Vessel | Finding | Measurement (as supplied, otherwise blank)\n"
                 "Impression: numbered list, abnormal findings only"),
)
_BY_ID = {p.id: p for p in PRESETS}


def get_preset(format_id: str | None) -> ReportFormat:
    key = ALIASES.get(format_id or "", format_id or "")
    return _BY_ID.get(key, _BY_ID[DEFAULT_FORMAT_ID])


def resolve_format(custom_text: str | None, format_id: str | None) -> ResolvedFormat:
    """The doctor's custom format alone when set, else the selected preset, else the default."""
    custom = (custom_text or "").strip()
    if custom:
        return ResolvedFormat(custom[:CUSTOM_FORMAT_MAX_CHARS], None, True)
    preset = get_preset(format_id)
    return ResolvedFormat(preset.format_text, preset.id, False)


def presets_payload() -> list[dict]:
    return [asdict(p) for p in PRESETS]
