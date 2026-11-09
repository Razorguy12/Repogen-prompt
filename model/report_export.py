"""PDF and Word rendering of a report in the on-screen house style.

Both formats are built from full_report (which carries the doctor's edits),
split by model.report_sections so headings look identical everywhere:
serif title, small uppercase blue section headings separated by thin rules,
and a shaded Impression block. Mirrors .report-doc in web/src/index.css.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from model.report_sections import parse_report

# Palette shared with the web UI (.report-doc).
TITLE = "#0f172a"
HEADING = "#1d4ed8"
BODY = "#1e293b"
RULE = "#e2e8f0"
IMPRESSION_BG = "#f8fafc"
MUTED = "#64748b"
LABEL_BG = "#eef2f7"


@dataclass
class ExportDocument:
    title: str
    full_report: str
    report_format: str | None = None
    meta: list[tuple[str, str]] = field(default_factory=list)   # header rows, e.g. Patient, Study date
    footer: str = ""                                            # disclaimer or "Finalized by ..."
    footer_is_warning: bool = True


# ---------------------------------------------------------------- shared helpers

_LIST_RE = re.compile(r"^\s*(?:([-*•])|(\d+[.)]))\s+(.*)$")
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)")


def _blocks(body: str):
    """Yield ("p", text) | ("bullet", text) | ("number", "1.", text) per non-empty line."""
    for line in body.split("\n"):
        if not line.strip():
            continue
        m = _LIST_RE.match(line)
        if m and m.group(1):
            yield ("bullet", m.group(3))
        elif m and m.group(2):
            yield ("number", m.group(2), m.group(3))
        else:
            yield ("p", line.strip())


def _runs(text: str):
    """Split inline markdown into (text, bold, italic) runs."""
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            yield part[2:-2], True, False
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            yield part[1:-1], False, True
        else:
            yield part, False, False


def _rl_markup(text: str) -> str:
    out = []
    for chunk, bold, italic in _runs(text.replace("\x00", "")):
        chunk = escape(chunk)
        out.append(f"<b>{chunk}</b>" if bold else f"<i>{chunk}</i>" if italic else chunk)
    return "".join(out)


# ---------------------------------------------------------------- PDF

def build_pdf(doc: ExportDocument, filename: str) -> str:
    pdf = SimpleDocTemplate(filename, pagesize=A4, rightMargin=0.8 * inch, leftMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch, title=doc.title)
    width = pdf.width
    title_style = ParagraphStyle("Title", fontName="Times-Bold", fontSize=17, leading=21,
                                 textColor=colors.HexColor(TITLE), spaceAfter=10)
    heading_style = ParagraphStyle("Heading", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
                                   textColor=colors.HexColor(HEADING), spaceAfter=4)
    body_style = ParagraphStyle("Body", fontName="Helvetica", fontSize=10, leading=16,
                                textColor=colors.HexColor(BODY), spaceAfter=3)
    list_style = ParagraphStyle("List", parent=body_style, leftIndent=14, bulletIndent=2)
    label_style = ParagraphStyle("Label", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                                 textColor=colors.HexColor(MUTED))
    meta_style = ParagraphStyle("Meta", fontName="Helvetica", fontSize=9.5, leading=12,
                                textColor=colors.HexColor(TITLE))

    parsed = parse_report(doc.full_report, doc.title, doc.report_format)
    story = [Paragraph(_rl_markup(parsed.title or doc.title or "RADIOLOGY REPORT"), title_style)]

    if doc.meta:
        rows = [[Paragraph(escape(k), label_style), Paragraph(escape(v), meta_style)] for k, v in doc.meta]
        table = Table(rows, colWidths=[1.3 * inch, width - 1.3 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(LABEL_BG)),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor(RULE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [table, Spacer(1, 10)]

    def body_flowables(body: str):
        items = []
        for block in _blocks(body):
            if block[0] == "bullet":
                items.append(Paragraph(_rl_markup(block[1]), list_style, bulletText="•"))
            elif block[0] == "number":
                items.append(Paragraph(_rl_markup(block[2]), list_style, bulletText=block[1]))
            else:
                items.append(Paragraph(_rl_markup(block[1]), body_style))
        return items

    for i, section in enumerate(parsed.sections):
        parts = []
        if section.heading:
            parts.append(Paragraph(escape(section.heading.upper()), heading_style))
        parts += body_flowables(section.body)
        if section.is_impression:
            box = Table([[parts]], colWidths=[width])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(IMPRESSION_BG)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ]))
            story += [Spacer(1, 8), box]
        else:
            if i > 0:
                story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(RULE),
                                        spaceBefore=6, spaceAfter=8))
            story.append(KeepTogether(parts[:2]) if len(parts) > 1 else parts[0] if parts else Spacer(1, 0))
            story += parts[2:]

    if doc.footer:
        story += [Spacer(1, 18), Paragraph(escape(doc.footer), ParagraphStyle(
            "Footer", fontName="Helvetica-Oblique", fontSize=7.5, leading=10,
            textColor=colors.HexColor("#92400e" if doc.footer_is_warning else MUTED)))]
    pdf.build(story)
    return filename


# ---------------------------------------------------------------- Word

def _set_run(run, size: float, color: str, bold=False, italic=False, font="Calibri", spacing_twips: int | None = None):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor.from_string(color.lstrip("#").upper())
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        fonts.set(qn(attr), font)
    if spacing_twips:
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), str(spacing_twips))
        rpr.append(sp)


def _shade(paragraph, fill: str):
    ppr = paragraph._element.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill.lstrip("#").upper())
    ppr.append(shd)


def _top_rule(paragraph):
    ppr = paragraph._element.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    top = OxmlElement("w:top")
    for k, v in (("w:val", "single"), ("w:sz", "4"), ("w:space", "8"), ("w:color", RULE.lstrip("#").upper())):
        top.set(qn(k), v)
    bdr.append(top)
    ppr.append(bdr)


def _indent(paragraph, fill: str | None):
    if fill:
        _shade(paragraph, fill)
        existing = paragraph.paragraph_format.left_indent or 0
        paragraph.paragraph_format.left_indent = existing + Pt(6)
        paragraph.paragraph_format.right_indent = Pt(6)


def _light_borders(table):
    tbl_pr = table._element.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{edge}")
        for k, v in (("w:val", "single"), ("w:sz", "4"), ("w:space", "0"), ("w:color", RULE.lstrip("#").upper())):
            el.set(qn(k), v)
        borders.append(el)
    for edge in ("left", "right", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tbl_pr.append(borders)


def _cell_fill(cell, fill: str):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill.lstrip("#").upper())
    cell._element.get_or_add_tcPr().append(shd)


def build_docx(doc: ExportDocument, filename: str) -> str:
    word = Document()
    for section in word.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    parsed = parse_report(doc.full_report, doc.title, doc.report_format)
    title = word.add_paragraph()
    title.paragraph_format.space_after = Pt(8)
    for text, bold, italic in _runs(parsed.title or doc.title or "RADIOLOGY REPORT"):
        _set_run(title.add_run(text), 17, TITLE, bold=True, italic=italic, font="Georgia")

    if doc.meta:
        table = word.add_table(rows=0, cols=2)
        table.autofit = False
        _light_borders(table)
        for label, value in doc.meta:
            cells = table.add_row().cells
            cells[0].width, cells[1].width = Inches(1.5), Inches(5.0)
            _cell_fill(cells[0], LABEL_BG)
            _set_run(cells[0].paragraphs[0].add_run(label), 8.5, MUTED, bold=True)
            _set_run(cells[1].paragraphs[0].add_run(value), 9.5, TITLE)
        for col, w in zip(table.columns, (Inches(1.5), Inches(5.0))):
            col.width = w
        word.add_paragraph().paragraph_format.space_after = Pt(2)

    for i, section in enumerate(parsed.sections):
        fill = IMPRESSION_BG if section.is_impression else None
        first_para = None
        if section.heading:
            h = word.add_paragraph()
            h.paragraph_format.space_before = Pt(14 if section.is_impression else 10 if i else 2)
            h.paragraph_format.space_after = Pt(3)
            h.paragraph_format.keep_with_next = True
            _set_run(h.add_run(section.heading.upper()), 8, HEADING, bold=True, spacing_twips=24)
            first_para = h
            _indent(h, fill)
        for block in _blocks(section.body):
            if block[0] == "bullet":
                p = word.add_paragraph(style="List Bullet")
                text = block[1]
            elif block[0] == "number":
                p = word.add_paragraph()
                p.paragraph_format.left_indent = Pt(18)
                p.paragraph_format.first_line_indent = Pt(-14)
                text = f"{block[1]} {block[2]}"
            else:
                p = word.add_paragraph()
                text = block[1]
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.35
            for chunk, bold, italic in _runs(text):
                _set_run(p.add_run(chunk), 10.5, BODY, bold=bold, italic=italic)
            _indent(p, fill)
            first_para = first_para or p
        if first_para is not None and i > 0 and not section.is_impression:
            _top_rule(first_para)

    if doc.footer:
        note = word.add_paragraph()
        note.paragraph_format.space_before = Pt(18)
        note.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _set_run(note.add_run(doc.footer), 7.5, "#92400e" if doc.footer_is_warning else MUTED, italic=True)

    word.save(filename)
    return filename
