"""Per-request assembly of the report system prompt to save tokens.

The prompt text in system_prompt.txt is never reworded. For each request we
send all general rules, and trim only two reference blocks that are long
and mostly irrelevant to a single case:

  * Section 0 glossary / ambiguous list: keep only entries whose
    abbreviation appears in the input. Entries that cannot apply are the
    only ones dropped, so rule 0.3 ("not in the glossary -> keep verbatim
    and flag") behaves exactly as with the full list.
  * Section 7 templates: keep only the sub-sections for the examination
    the input describes (keyword match, deliberately broad). If no
    examination can be recognised, the whole of section 7 is kept.

Set REPORT_PROMPT_TRIM=0 to send the full prompt (instant rollback).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
_HEADER_RE = re.compile(r"(\n=+\n(\d+b?)\. [^\n]*\n=+\n)")

# Section-7 groups: sub-section numbers and the input keywords that select them.
# Broad on purpose: including an extra template is harmless; missing one is not.
_US = r"usg|ultra ?sound|sonograph|\bus\b|\bscan\b|echo"
SECTION7_GROUPS: list[tuple[tuple[str, ...], str]] = [
    (("7.1",), r"x-?ray|xray|\bcxr\b|radiograph|\bxr\b|\bdx\b|chest film|\bpa view|\bap view|\bcp ?angle|\bcpa\b|"
               r"\bbvm\b|\bctr\b|\b[rl][uml]z\b|(upper|mid|lower) zone|hilar|hila\b"),
    (("7.2",), r"abdom|liver|hepat|gall ?bladder|\bgb\b|pancrea|spleen|splen|\bcbd\b|bowel|append|\bihbr|"
               r"\bruq\b|\bluq\b|\brif\b|\blif\b|portal"),
    (("7.3",), r"\bkub\b|kidney|renal|ureter|bladder|\bub\b|calcul|stone|\bpcs\b|hydroneph|\bhdu?n\b|\bpuj\b|"
               r"\bvuj\b|\bupj\b|\buvj\b|prostat|\bpvru?\b|post[- ]void"),
    (("7.4",), r"pelvi|uter|ovar|endometri|adnex|cervix|\bpod\b|douglas|transvaginal|\btvs\b|\btas\b|fibroid|"
               r"follic|prostat|seminal|o-?rads"),
    (("7.5",), r"neck|thyroid|nodule|parotid|submandibular|lymph ?node|\bln\b|tirads|isthmus|cervical node"),
    (("7.6",), r"pleura|effusion|lung (ultra|us|usg)|b-?lines|lung sliding|(usg|ultrasound|us) (of )?(the )?chest|"
               r"thorax us|empyema"),
    (("7.7",), r"neonat|newborn|preterm|infant|fontanel|cranial (us|usg|ultrasound)|\bivh\b|\bgmh\b|\bpvl\b|papile|"
               r"caudothalamic|germinal matrix"),
    (("7.8", "7.9", "7.10", "7.11"),
     r"pregnan|gestation|fetus|fetal|foet|obstet|antenatal|\bobs\b|\banc\b|\bgs\b|\bmsd\b|yolk|\bcrl\b|\bnt\b|"
     r"nuchal|nasal bone|\bbpd\b|\bhc\b|\bac\b|\bfl\b|femur length|\befw\b|liquor|\bafi\b|\bsdp\b|\bsvp\b|"
     r"placent|\blmp\b|\bedd\b|tiffa|anomaly scan|level ?ii|growth scan|wellbeing|well-being|\biugr\b|\bfgr\b|"
     r"\bsliu[pf]?\b|\biup\b|\bga\b|\bpog\b|\d+ ?(weeks?|wks?) ?(\+ ?\d|\d+ ?days?|of gestation|gestation|ga\b|pog)|"
     r"cervical length|twin|chorion|amnion|\bfhr\b|\bfhs\b|cardiac activity|cephalic|breech|transverse lie|"
     r"umbilical|cord insertion|nuchal cord|baby|\bsex\b|gender"),
    (("7.12", "7.13", "7.14", "7.15", "7.16"),
     r"doppler|duplex|colou?r flow|\bpsv\b|\bedv\b|\bri\b|\bpi\b|s/d|waveform|phasic|tardus|stenos|occlu|\bdvt\b|"
     r"thromb|carotid|vertebral|\b[ice]ca\b|\bimt\b|\bcfa\b|\bsfa\b|\bata\b|\bpta\b|\bdpa\b|\bcfv\b|\bsfv\b|"
     r"\bgsv\b|\bssv\b|\bsfj\b|\bspj\b|varicos|reflux|venous|arterial|artery|vein|\bua\b|\bmca\b|\butas?\b|"
     r"uterine arter|ductus|\bdv\b|\bcpr\b|aedf|redf|fistula|\bavf\b|vascular|velocity"),
]
SECTION7_GROUPS.append(
    (("7.17",), r"\bct\b|\bcect\b|\bncct\b|\bhrct\b|\bcta\b|\bmri\b|\bmr\b|\bmra\b|computed tomograph|"
                r"magnetic resonance|mammo|fluoro|\bpet\b|angiogra|\bmsk\b|\bdexa\b|\bivp\b|barium"))
ALWAYS_SECTION7 = ("7.17",)


def _sections(text: str) -> list[tuple[str | None, str, str]]:
    """[(number, header_block, body)] with the preamble as number None."""
    parts = _HEADER_RE.split(text)
    out = [(None, "", parts[0])]
    for i in range(1, len(parts), 3):
        out.append((parts[i + 1], parts[i], parts[i + 2]))
    return out


# ----------------------------------------------------------------- glossary

def _entry_terms(entry_first_line: str) -> list[str]:
    """Abbreviations named by one glossary line, e.g. 'RUZ / RMZ / RLZ - ...' -> [RUZ, RMZ, RLZ]."""
    head = entry_first_line.strip().split(" - ", 1)[0]
    head = re.sub(r"\([^)]*\)", "", head)
    terms = {head.strip()}
    for part in head.split(" / "):
        part = part.strip()
        if part:
            terms.add(part)
            # 'CP angle', 'ET tube', 'AV fistula': the leading abbreviation counts too.
            terms.add(part.split(" ")[0])
    return [t for t in terms if t and (len(t) >= 2 or "/" in t)]


def _term_in(term: str, haystack: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", haystack, re.IGNORECASE) is not None


def _filter_entries(block: str, haystack: str) -> str:
    """Keep category headers that still have entries, and entries whose terms occur in the input."""
    lines = block.split("\n")
    kept: list[str] = []
    header: str | None = None
    entry: list[str] = []
    header_has_entries = False

    def flush_entry():
        nonlocal entry, header_has_entries, header
        if entry and any(_term_in(t, haystack) for t in _entry_terms(entry[0])):
            if header is not None and not header_has_entries:
                kept.append(header)
                header_has_entries = True
            kept.extend(entry)
        entry = []

    for line in lines:
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            flush_entry()
            entry = [line]
        elif line.startswith("    ") and entry:
            entry.append(line)  # continuation of a wrapped entry
        else:
            flush_entry()
            if line.strip():
                header, header_has_entries = line, False
                if line.rstrip().endswith(":") is False:
                    kept.append(line)  # plain prose line: always keep
                    header = None
            else:
                if kept and kept[-1] != "":
                    kept.append("")
    flush_entry()
    return "\n".join(kept)


def _trim_section0(body: str, haystack: str) -> str:
    g = re.search(r"^RADIOLOGY GLOSSARY \(", body, re.M)
    a = re.search(r"^AMBIGUOUS ABBREVIATIONS \(", body, re.M)
    if not g or not a or a.start() < g.start():
        return body
    g_start, a_start = g.start(), a.start()
    rules = body[:g_start]
    glossary_title, _, glossary = body[g_start:a_start].partition("\n")
    ambiguous_title, _, ambiguous = body[a_start:].partition("\n")
    glossary_kept = _filter_entries(glossary, haystack).strip("\n")
    ambiguous_kept = "\n".join(
        line for line in ambiguous.split("\n")
        if line.strip() and any(_term_in(t, haystack) for t in _entry_terms(line))
    )
    out = rules + glossary_title + " - entries for abbreviations found in this input\n"
    out += (glossary_kept + "\n") if glossary_kept.strip() else "  (none of the glossary abbreviations occur in this input)\n"
    if ambiguous_kept:
        out += "\n" + ambiguous_title + "\n" + ambiguous_kept + "\n"
    return out + "\n"


# ----------------------------------------------------------------- section 7

def _trim_section7(body: str, haystack: str) -> str:
    chunks = re.split(r"\n(?=7\.\d+ )", body)
    intro, subs = chunks[0], chunks[1:]
    wanted: set[str] = set(ALWAYS_SECTION7)
    matched_any = False
    for numbers, pattern in SECTION7_GROUPS:
        if re.search(pattern, haystack, re.IGNORECASE):
            wanted.update(numbers)
            matched_any = True
    if not matched_any:
        return body  # unknown examination: keep every template
    kept = [c for c in subs if c.split(" ", 1)[0] in wanted]
    return "\n".join([intro, *kept]).rstrip("\n") + "\n\n"


# ----------------------------------------------------------------- public

@lru_cache(maxsize=1)
def full_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def trimming_enabled() -> bool:
    return os.getenv("REPORT_PROMPT_TRIM", "1").strip().lower() not in {"0", "false", "no", "off"}


def build_system_prompt(findings: str, report_format: str | None = None) -> str:
    """System prompt for one case. Falls back to the full prompt if trimming is off or parsing fails."""
    text = full_prompt()
    if not trimming_enabled():
        return text
    haystack = f"{findings or ''}\n{report_format or ''}"
    try:
        out = []
        for number, header, body in _sections(text):
            if number == "0":
                body = _trim_section0(body, haystack)
            elif number == "7":
                body = _trim_section7(body, haystack)
            out.append(header + body)
        return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()
    except Exception:  # never let an optimisation break generation
        return text
