"""Printable calendar (PDF): large type, one row per medicine with its official pack photo, dose per moment of the day.

Everything printed comes from confirmed fields: the dose as the caregiver confirmed it, the medicine name and photo from
AEMPS CIMA. A second block lists what is NOT included and why, then the findings to review with their quoted sources, then the
consulted sources and the date. There is no "all clear" mark anywhere.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .findings import NOT_AN_INTERACTION_CHECK
from .plan import SLOT_LABELS, Plan
from .schedule import SLOTS

DISCLAIMER = ("Este plan se ha preparado con la hoja de medicación que el cuidador ha confirmado línea a línea. Es una ayuda para "
              "organizar la medicación: no sustituye al médico ni al farmacéutico. Consulte con su farmacéutico antes de usarlo.")


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
    return f'{number}<br/><font size="10">{unit}</font>'


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
                            title="Plan de medicación", author="med-table (prototipo)")
    story = [Paragraph("Plan de medicación", title),
             Paragraph(f"Paciente: {patient or '________________________'} &nbsp;&nbsp; Fecha del plan: {plan.generated.strftime('%d/%m/%Y')}", big),
             Spacer(1, 4 * mm)]

    meds: dict[str, list] = {}
    for e in plan.entries:
        meds.setdefault(e.pack.medicine.cn, []).append(e)
    header = [Paragraph("<b>Medicamento</b>", base), ""] + [Paragraph(f"<b>{SLOT_LABELS[s]}</b>", ParagraphStyle("h", parent=base, alignment=1)) for s in SLOTS] + [Paragraph("<b>Notas del cuidador</b>", base)]
    rows = [header]
    for entries in meds.values():
        first = entries[0]
        photo = _photo(first.pack.medicine, photo_dir)
        cells = {e.slot: Paragraph(_dose_markup(e), dose) for e in entries}
        remarks = "; ".join(dict.fromkeys(e.line.remarks for e in entries if e.line.remarks))
        rows.append([Image(str(photo), width=26 * mm, height=15 * mm, kind="proportional") if photo else "",
                     Paragraph(first.name, name)] + [cells.get(s, Paragraph("-", dose)) for s in SLOTS] + [Paragraph(remarks, base)])
    if len(rows) == 1:
        rows.append(["", Paragraph("No hay medicación en el plan.", big), "", "", "", "", ""])
    table = Table(rows, colWidths=[30 * mm, 66 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm, 52 * mm], repeatRows=1)
    table.setStyle(TableStyle([("SPAN", (0, 0), (1, 0)), ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#888888")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [table, Spacer(1, 5 * mm), Paragraph(DISCLAIMER, small)]

    if plan.not_included:
        block = [Paragraph("<b>No incluido en el calendario</b>", ParagraphStyle("hn", parent=red, fontSize=13))]
        block += [Paragraph(f"&bull; {what}: {why}", red) for what, why in plan.not_included]
        story += [Spacer(1, 4 * mm), KeepTogether(block)]
    review = sorted((f for f in plan.findings if f.kind != "unverified_item"), key=lambda f: f.severity != "review")
    if review:
        block = [Paragraph("<b>Para revisar con su farmacéutico</b>", ParagraphStyle("hr", parent=base, fontSize=13))]
        for f in review:
            block.append(Paragraph(f"&bull; {f.text('es')}", base))
            if f.source:
                block.append(Paragraph(f"Fuente: {f.source}", small))
        story += [Spacer(1, 4 * mm), KeepTogether(block)]
    story += [Spacer(1, 3 * mm), Paragraph(NOT_AN_INTERACTION_CHECK["es"].replace("No se encontró ninguna mención en las secciones revisadas. ", ""), small),
              Paragraph("Fuentes consultadas: " + (" | ".join(plan.sources) or "ninguna"), small)]
    doc.build(story)
    return out
