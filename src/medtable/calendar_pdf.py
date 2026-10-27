"""Printable calendar (PDF): large type, one row per medicine with its official pack photo, dose per moment of the day.

Everything printed comes from confirmed fields: the dose as the caregiver confirmed it, the medicine name and photo from
AEMPS CIMA. A second block lists what is NOT included and why, then the findings to review with their quoted sources, then the
consulted sources and the date. There is no "all clear" mark anywhere.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .findings import NOT_A_FULL_CHECK
from .plan import SLOT_LABELS, Plan
from .schedule import SLOTS

DISCLAIMER = ("This plan was prepared from the medication sheet that the caregiver confirmed line by line. It is an aid to organise "
              "medication: it does not replace the doctor or the pharmacist. Ask your pharmacist before using it.")


def _photo(medicine, photo_dir: Path, local_dir: Path = Path("data/cima/images/full")) -> Path | None:
    """The official pack photo (preferred) or dosage-form photo: from the local CIMA download, else fetched and cached."""
    for kind in ("materialas", "formafarmac"):
        local = local_dir / kind / f"{medicine.nregistro}.jpg"
        if local.exists():
            return local
        url = medicine.photos.get(kind)
        if url:
            cached = photo_dir / f"{medicine.nregistro}_{kind}.jpg"
            if not cached.exists():
                try:
                    photo_dir.mkdir(parents=True, exist_ok=True)
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        cached.write_bytes(resp.read())
                except OSError:
                    continue
            return cached
    return None


def _dose_markup(entry) -> str:
    """Big number, smaller unit below it, so the unit word never breaks across lines."""
    number, unit = entry.written().split(" ", 1)
    return f'{esc(number)}<br/><font size="10">{esc(unit)}</font>'


def render_pdf(plan: Plan, out: Path, patient: str = "", photo_dir: Path = Path("data/cache/photos")) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=11, leading=14, alignment=TA_LEFT)
    big = ParagraphStyle("big", parent=base, fontSize=15, leading=18)
    name = ParagraphStyle("name", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=15)
    dose = ParagraphStyle("dose", parent=base, fontName="Helvetica-Bold", fontSize=22, leading=24, alignment=1)
    small = ParagraphStyle("small", parent=base, fontSize=8.5, leading=10.5, textColor=colors.HexColor("#444444"))
    red = ParagraphStyle("red", parent=base, textColor=colors.HexColor("#a00000"))
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=24, leading=28)

    doc = SimpleDocTemplate(str(out), pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Medication plan", author="med-table (prototype)")
    story = [Paragraph("Medication plan", title),
             Paragraph(f"Patient: {esc(patient) or '________________________'} &nbsp;&nbsp; Plan date: {plan.generated.strftime('%d %b %Y')}", big),
             Spacer(1, 4 * mm)]

    meds: dict[str, list] = {}
    for e in plan.entries:
        meds.setdefault(e.pack.medicine.cn, []).append(e)
    header = [Paragraph("<b>Medicine</b>", base), ""] + [Paragraph(f"<b>{SLOT_LABELS[s]}</b>", ParagraphStyle("h", parent=base, alignment=1)) for s in SLOTS] + [Paragraph("<b>Caregiver's notes</b>", base)]
    rows = [header]
    for entries in meds.values():
        first = entries[0]
        photo = _photo(first.pack.medicine, photo_dir)
        cells = {}
        for slot in SLOTS:  # two entries for one pack and slot are both printed, never one over the other
            marks = [_dose_markup(e) for e in entries if e.slot == slot]
            if marks:
                cells[slot] = Paragraph("<br/>+<br/>".join(marks), dose)
        remarks = esc("; ".join(dict.fromkeys(e.line.remarks for e in entries if e.line.remarks)))
        rows.append([Image(str(photo), width=34 * mm, height=22 * mm, kind="proportional") if photo else "",
                     Paragraph(esc(first.name), name)] + [cells.get(s, Paragraph("-", dose)) for s in SLOTS] + [Paragraph(remarks, base)])
    if len(rows) == 1:
        rows.append(["", Paragraph("No medication in the plan.", big), "", "", "", "", ""])
    table = Table(rows, colWidths=[38 * mm, 62 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm, 52 * mm], repeatRows=1)
    table.setStyle(TableStyle([("SPAN", (0, 0), (1, 0)), ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#888888")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [table, Spacer(1, 5 * mm), Paragraph(DISCLAIMER, small)]

    if plan.not_included:
        block = [Paragraph("<b>Not included in the calendar</b>", ParagraphStyle("hn", parent=red, fontSize=13))]
        block += [Paragraph(f"&bull; {esc(what)}: {esc(why)}", red) for what, why in plan.not_included]
        story += [Spacer(1, 4 * mm), KeepTogether(block)]
    review = sorted((f for f in plan.findings if f.kind != "unverified_item"), key=lambda f: f.severity != "review")
    if review:
        block = [Paragraph("<b>To review with your pharmacist</b>", ParagraphStyle("hr", parent=base, fontSize=13))]
        for f in review:
            block.append(Paragraph(f"&bull; {esc(f.text())}", base))
            if f.source:
                block.append(Paragraph(f"Source: {esc(f.source)}", small))
        story += [Spacer(1, 4 * mm), KeepTogether(block)]
    checked = ("Checks done: duplicate active ingredient, ATC group, expiry read from the code and match with the sheet"
               + (", and verbatim quotes from sections 4.2 and 4.5 of the leaflets (SmPC; quotes stay in the original Spanish)." if plan.smpc_used else ". The leaflets (SmPC) were NOT consulted."))
    missing = [f for f in plan.findings if f.kind == "smpc_unavailable"]
    if missing:
        checked += " Some leaflet section could not be checked (see above)."
    story += [Spacer(1, 3 * mm), Paragraph(esc(checked), small),
              Paragraph(esc(NOT_A_FULL_CHECK + " No warning does not mean the plan is safe."), small),
              Paragraph("Sources consulted: " + esc(" | ".join(plan.sources) or "none"), small)]
    doc.build(story)
    return out
