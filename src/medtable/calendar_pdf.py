"""Printable calendar (PDF), two pages.

Page 1 is the page for the fridge: who it is for, one row per medicine with its official pack photo, the dose for each moment of the
day (pictogram, name and reminder time in the column header), the caregiver's notes per medicine, and a notes box for the whole plan
(typed, or ruled lines to write on by hand). Page 2 is for the pharmacist and the caregiver: what is NOT in the calendar and why, the
findings to review with their quoted sources, the checks that were and were not run, and the sources and date. There is no
"all clear" mark anywhere, and page 1 says when something was left out.

Everything printed comes from confirmed fields: the dose as the caregiver confirmed it, the medicine name and photo from AEMPS CIMA.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import Flowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .findings import NOT_A_FULL_CHECK
from .plan import DEFAULT_TIMES, SLOT_LABELS, Plan
from .schedule import SLOTS

DISCLAIMER = ("This plan was prepared from the medication sheet that the caregiver confirmed line by line. It is an aid to organise "
              "medication: it does not replace the doctor or the pharmacist. Ask your pharmacist before using it.")
TINT = {"breakfast": "#fff1c2", "lunch": "#ffdfb0", "dinner": "#f6d3d3", "bedtime": "#d9def5"}
INK = colors.HexColor("#1a1a1a")


def _photo(medicine, photo_dir: Path, local_dir: Path = Path("data/cima/images/full")) -> Path | None:
    """The official pack photo (preferred) or dosage-form photo: from the local CIMA download, else fetched and cached."""
    from .resolve import BUNDLED
    for kind in ("materialas", "formafarmac"):
        for local in (local_dir / kind / f"{medicine.nregistro}.jpg", BUNDLED / "photos" / kind / f"{medicine.nregistro}.jpg"):
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
    days = entry.days_text()
    return f'{esc(number)}<br/><font size="11">{esc(unit)}</font>' + (f'<br/><font size="10"><b>{esc(days)}</b></font>' if days else "")


class SlotIcon(Flowable):
    """A simple pictogram for a moment of the day: sunrise, sun, sunset, moon. Drawn with vector shapes, no image files."""

    def __init__(self, slot: str, size: float = 14 * mm):
        super().__init__()
        self.slot, self.size, self.hAlign = slot, size, "CENTER"

    def wrap(self, avail_w, avail_h):
        return self.size, self.size

    def _rays(self, cx, cy, r1, r2, angles):
        import math
        for a in angles:
            self.canv.line(cx + r1 * math.cos(math.radians(a)), cy + r1 * math.sin(math.radians(a)),
                           cx + r2 * math.cos(math.radians(a)), cy + r2 * math.sin(math.radians(a)))

    def draw(self):
        c, s = self.canv, self.size
        cx, cy = s / 2, s / 2
        c.saveState()
        c.setLineWidth(1.4)
        if self.slot == "breakfast":      # sunrise: half sun above the horizon, rays above it
            c.setFillColor(colors.HexColor("#f5b800")); c.setStrokeColor(colors.HexColor("#c78a00"))
            c.wedge(cx - s * 0.28, s * 0.22 - s * 0.28, cx + s * 0.28, s * 0.22 + s * 0.28, 0, 180, stroke=1, fill=1)
            self._rays(cx, s * 0.22, s * 0.36, s * 0.5, (20, 55, 90, 125, 160))
            c.setStrokeColor(INK); c.line(s * 0.05, s * 0.22, s * 0.95, s * 0.22)
        elif self.slot == "lunch":        # full sun
            c.setFillColor(colors.HexColor("#f5b800")); c.setStrokeColor(colors.HexColor("#c78a00"))
            c.circle(cx, cy, s * 0.22, stroke=1, fill=1)
            self._rays(cx, cy, s * 0.32, s * 0.48, range(0, 360, 45))
        elif self.slot == "dinner":       # sunset: low half sun, no rays above, water lines below
            c.setFillColor(colors.HexColor("#e2572b")); c.setStrokeColor(colors.HexColor("#a53a16"))
            c.wedge(cx - s * 0.3, s * 0.45 - s * 0.3, cx + s * 0.3, s * 0.45 + s * 0.3, 0, 180, stroke=1, fill=1)
            c.setStrokeColor(INK)
            for y in (0.45, 0.30, 0.15):
                c.line(s * (0.08 + (0.45 - y)), s * y, s * (0.92 - (0.45 - y)), s * y)
        else:                             # bedtime: crescent moon and a star
            c.setFillColor(colors.HexColor("#3b4a9c")); c.setStrokeColor(colors.HexColor("#3b4a9c"))
            c.circle(cx - s * 0.05, cy, s * 0.33, stroke=0, fill=1)
            c.setFillColor(colors.HexColor(TINT["bedtime"]))
            c.circle(cx + s * 0.1, cy + s * 0.07, s * 0.29, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#3b4a9c"))
            c.circle(cx + s * 0.34, cy + s * 0.3, s * 0.05, stroke=0, fill=1)
        c.restoreState()


def render_pdf(plan: Plan, out: Path, patient: str = "", photo_dir: Path = Path("data/cache/photos"), notes: str = "",
               times: dict[str, str] | None = None, changes=None) -> Path:
    """`changes`: a medtable.changes.Changes when the plan was reopened from a saved one; listed on page 2 for the pharmacist."""
    out.parent.mkdir(parents=True, exist_ok=True)
    times = {**DEFAULT_TIMES, **(times or {})}
    patient, notes = patient.strip(), notes.strip()
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=12, leading=15, alignment=TA_LEFT, textColor=INK)
    big = ParagraphStyle("big", parent=base, fontSize=17, leading=21)
    name = ParagraphStyle("name", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=16)
    dose = ParagraphStyle("dose", parent=base, fontName="Helvetica-Bold", fontSize=26, leading=28, alignment=TA_CENTER)
    head = ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=16, alignment=TA_CENTER)
    clock = ParagraphStyle("clock", parent=base, fontSize=12, leading=14, alignment=TA_CENTER)
    small = ParagraphStyle("small", parent=base, fontSize=9, leading=11.5, textColor=colors.HexColor("#444444"))
    red = ParagraphStyle("red", parent=base, textColor=colors.HexColor("#a00000"))
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=28, leading=32)
    quote_style = ParagraphStyle("quote", parent=base, fontName="Helvetica-Oblique", fontSize=10.5, leading=13.5, leftIndent=10, textColor=colors.HexColor("#333333"))
    who = esc(patient) if patient else "_" * 28

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        for i, text in enumerate(simpleSplit(DISCLAIMER, "Helvetica", 8, 225 * mm)):
            canvas.drawString(14 * mm, (9.5 - 3.6 * i) * mm, text)
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 7 * mm, f"Page {document.page} of 2")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out), pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=11 * mm, bottomMargin=16 * mm,
                            title="Medication plan", author="med-table (prototype)")

    # ---- page 1: the calendar ---------------------------------------------------------------------------------------------
    story = [Paragraph("Medication plan", title),
             Paragraph(f"<b>For:</b> {who} &nbsp;&nbsp;&nbsp; <b>Date:</b> {plan.generated.strftime('%d %b %Y')}", big),
             Spacer(1, 4 * mm)]
    meds: dict[str, list] = {}
    for e in plan.entries:
        meds.setdefault(e.pack.medicine.cn, []).append(e)
    header = [Paragraph("<b>Medicine</b>", name), ""]
    for s in SLOTS:
        header.append([SlotIcon(s), Paragraph(SLOT_LABELS[s], head), Paragraph(esc(times[s]), clock)])
    header.append(Paragraph("<b>Notes</b>", name))
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
        rows.append([Image(str(photo), width=34 * mm, height=24 * mm, kind="proportional") if photo else "",
                     Paragraph(esc(first.name.replace("/", "/ ")), name)] + [cells.get(s, Paragraph("-", dose)) for s in SLOTS] + [Paragraph(remarks, base)])
    if len(rows) == 1:
        rows.append(["", Paragraph("No medication in the plan.", big), "", "", "", "", "", ""])
    table = Table(rows, colWidths=[36 * mm, 66 * mm, 29 * mm, 29 * mm, 29 * mm, 29 * mm, 50 * mm], repeatRows=1)
    style = [("SPAN", (0, 0), (1, 0)), ("GRID", (0, 0), (-1, -1), 0.9, colors.HexColor("#555555")), ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#e8eef5")),
             ("BACKGROUND", (6, 0), (6, 0), colors.HexColor("#e8eef5")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, 0), 1.6, INK)]
    for i, s in enumerate(SLOTS):
        style.append(("BACKGROUND", (2 + i, 0), (2 + i, 0), colors.HexColor(TINT[s])))
    table.setStyle(TableStyle(style))
    story.append(table)
    if plan.not_included:
        story += [Spacer(1, 3 * mm), Paragraph(f"<b>{len(plan.not_included)} item(s) are NOT in this calendar.</b> See page 2 for what and why.", red)]

    ruled = [f"Doctor: {'_' * 30} &nbsp; Phone: {'_' * 20}", f"Pharmacy: {'_' * 28} &nbsp; Phone: {'_' * 20}", f"Other: {'_' * 60}"]
    body = [Paragraph(esc(line) or "&nbsp;", base) for line in notes.splitlines()] if notes else [Paragraph(r, base) for r in ruled]
    box = Table([[Paragraph("<b>Notes for the whole plan</b>", name)], *[[p] for p in body]], colWidths=[268 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#555555")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 7 if not notes else 3)]))
    story += [Spacer(1, 4 * mm), KeepTogether([box])]

    # ---- page 2: for the pharmacist and the caregiver -----------------------------------------------------------------------
    story += [PageBreak(), Paragraph("For the pharmacist and the caregiver", title), Paragraph(f"<b>Plan for:</b> {who} &nbsp;&nbsp; <b>Date:</b> {plan.generated.strftime('%d %b %Y')}", big),
              Spacer(1, 4 * mm)]
    if plan.not_included:
        block = [Paragraph("<b>Not included in the calendar</b>", ParagraphStyle("hn", parent=red, fontName="Helvetica-Bold", fontSize=15, leading=18))]
        block += [Paragraph(f"&bull; {esc(what)}: {esc(why)}", red) for what, why in plan.not_included]
        story += [KeepTogether(block), Spacer(1, 4 * mm)]
    if changes:
        block = [Paragraph("<b>Changes since the saved plan</b>", ParagraphStyle("hc", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18))]
        block += [Paragraph(f"&bull; New: {esc(n)}", base) for n in changes.new]
        block += [Paragraph(f"&bull; Not seen in the new photos: {esc(n)}", base) for n in changes.not_seen]
        block += [Paragraph(f"&bull; {esc(n)}: {esc('; '.join(d))}", base) for n, d in changes.amounts]
        story += [KeepTogether(block), Spacer(1, 4 * mm)]
    review = sorted((f for f in plan.findings if f.kind != "unverified_item"), key=lambda f: f.severity != "review")
    if review:
        story.append(Paragraph("<b>To review with your pharmacist</b>", ParagraphStyle("hr", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18)))
        for f in review:
            block = [Spacer(1, 2 * mm), Paragraph(f"<b>{esc(f.title)}.</b> {esc(f.lead())}", base)]
            if f.quote:
                block.append(Paragraph(esc(f.quote), quote_style))
            if f.source:
                block.append(Paragraph(f"Source: {esc(f.source)}", small))
            story.append(KeepTogether(block))
    elif not plan.not_included:
        story.append(Paragraph("No points were raised by the checks listed below. That does not mean the plan is safe.", base))
    checked = ("Checks done: duplicate active ingredient, ATC group, expiry read from the code and match with the sheet"
               + (", and verbatim quotes from sections 4.2 and 4.5 of the leaflets (SmPC; quotes stay in the original Spanish)." if plan.smpc_used else ". The leaflets (SmPC) were NOT consulted."))
    if any(f.kind == "smpc_unavailable" for f in plan.findings):
        checked += " Some leaflet section could not be checked (see above)."
    story += [Spacer(1, 5 * mm), Paragraph(esc(checked), small),
              Paragraph(esc(NOT_A_FULL_CHECK + " No warning does not mean the plan is safe."), small),
              Paragraph("Sources consulted: " + esc(" | ".join(plan.sources) or "none"), small)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out
