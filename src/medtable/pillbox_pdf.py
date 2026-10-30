"""Printable weekly pill organiser sheet (PDF, one page): seven days by four moments of the day.

Many older people take their medicines from a weekly pill organiser that someone fills once a week. This page is the guide for
filling it: each cell lists what goes into that compartment, only on the days the caregiver chose. It is built only from the plan's
entries (confirmed doses of verified, unexpired packs), so what is left out of the plan is left out here too, and the page says so.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape as esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .calendar_pdf import DISCLAIMER, INK, TINT, SlotIcon
from .plan import DAY_NAMES, DEFAULT_TIMES, SLOT_LABELS, Plan
from .schedule import SLOTS

FORM_WORDS = r"\b(COMPRIMID|CAPSUL|SOBRE|SOLUCI|SUSPENSI|GRANULADO|PARCHE|POLVO|JARABE|GOTAS|EFG\b)"


def short_name(name: str) -> str:
    """'SINTROM 4 mg COMPRIMIDOS' -> 'SINTROM 4 mg': the name and strength, without the pharmaceutical form, to fit a small cell."""
    cut = re.split(FORM_WORDS, name.upper(), maxsplit=1)[0]
    return name[:len(cut)].strip(" ,") or name


def week_cells(plan: Plan) -> dict[tuple[str, int], list[tuple[str, str]]]:
    """(slot, weekday) -> what goes into that compartment: [('1/2 tablet', 'SINTROM 4 mg'), ...]."""
    cells: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for e in plan.entries:
        for day in e.line.days:
            cells.setdefault((e.slot, day), []).append((e.written(), short_name(e.name)))
    return cells


def render_pillbox(plan: Plan, out: Path, patient: str = "", times: dict[str, str] | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    times = {**DEFAULT_TIMES, **(times or {})}
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=12, textColor=INK)
    cell = ParagraphStyle("cell", parent=base, fontSize=10.5, leading=12.5, spaceAfter=4)
    head = ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=TA_CENTER)
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=24, leading=28)
    big = ParagraphStyle("big", parent=base, fontSize=14, leading=18)
    red = ParagraphStyle("red", parent=base, fontSize=11, textColor=colors.HexColor("#a00000"))
    who = esc(patient.strip()) if patient.strip() else "_" * 28

    cells = week_cells(plan)
    rows = [[""] + [Paragraph(day, head) for day in DAY_NAMES]]
    for slot in SLOTS:
        label = [SlotIcon(slot, 10 * mm), Paragraph(f"<b>{esc(SLOT_LABELS[slot])}</b><br/>{esc(times[slot])}", ParagraphStyle("s", parent=base, alignment=TA_CENTER))]
        rows.append([label] + [[Paragraph(f"<b>{esc(dose)}</b><br/>{esc(name)}", cell) for dose, name in cells.get((slot, d), [])] or Paragraph("-", head) for d in range(7)])
    table = Table(rows, colWidths=[27 * mm] + [34.4 * mm] * 7, rowHeights=[9 * mm] + [33 * mm] * 4)
    style = [("GRID", (0, 0), (-1, -1), 0.9, colors.HexColor("#555555")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")), ("LINEBELOW", (0, 0), (-1, 0), 1.6, INK)]
    for i, slot in enumerate(SLOTS, 1):
        style.append(("BACKGROUND", (0, i), (0, i), colors.HexColor(TINT[slot])))
    table.setStyle(TableStyle(style))

    story = [Paragraph("Weekly pill organiser", title),
             Paragraph(f"<b>For:</b> {who} &nbsp;&nbsp;&nbsp; <b>Plan of:</b> {plan.generated.strftime('%d %b %Y')}", big), Spacer(1, 3 * mm),
             Paragraph("Fill each compartment with what its box says. A dash means nothing at that time.", base), Spacer(1, 3 * mm), table]
    if plan.not_included:
        story += [Spacer(1, 2 * mm), Paragraph(f"<b>{len(plan.not_included)} item(s) are NOT on this page</b> (see page 2 of the medication plan).", red)]
    story += [Spacer(1, 3 * mm), Paragraph("Filled on: ______________ &nbsp;&nbsp; by: ______________ &nbsp;&nbsp; Checked by: ______________", base)]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        for i, text in enumerate(simpleSplit(DISCLAIMER, "Helvetica", 8, 270 * mm)):
            canvas.drawString(12 * mm, (8 - 3.4 * i) * mm, text)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=13 * mm,
                            title="Weekly pill organiser", author="med-table (prototype)")
    doc.build(story, onFirstPage=footer)
    return out
