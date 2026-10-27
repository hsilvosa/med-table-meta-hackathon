"""What the printed calendar says, read back from the PDF itself."""

from datetime import timedelta

import pypdfium2 as pdfium

from fixtures import ACENOCUMAROL, FakeSmpc, IBUPROFENO, LORAZEPAM, METFORMINA_850, OMEPRAZOL, TODAY, pack
from medtable.calendar_pdf import render_pdf
from medtable.plan import build_plan
from medtable.rules import check_packs, meal_notes
from medtable.schedule import SLOTS, Line, reconcile


def line(text, remarks="", confirmed=True, **doses):
    return Line(text, {**dict.fromkeys(SLOTS, "0"), **doses}, remarks, confirmed=confirmed)


def pdf_text(tmp_path):
    lines = [line("Metformina 850 mg", "con las comidas", breakfast="1", dinner="1/2"), line("Lorazepam 1 mg", bedtime="1"),
             line("Atorvastatina 20 mg", dinner="1"), line("Omeprazol 20 mg", breakfast="1", confirmed=False)]
    packs = [pack(METFORMINA_850), pack(LORAZEPAM, TODAY - timedelta(days=2)), pack(IBUPROFENO), pack(ACENOCUMAROL), pack(OMEPRAZOL)]
    recon = reconcile(lines, packs)
    plan = build_plan(lines, recon, check_packs(packs, FakeSmpc(), TODAY) + meal_notes(packs, FakeSmpc()) + recon.findings, TODAY)
    out = render_pdf(plan, tmp_path / "plan.pdf", "Test patient")
    doc = pdfium.PdfDocument(str(out))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_pdf_carries_the_safeguards_and_the_confirmed_doses(tmp_path):
    text = pdf_text(tmp_path)
    flat = " ".join(text.split())
    assert "does not replace the doctor or the pharmacist" in flat
    assert "Not included in the calendar" in flat and "expired" in flat and "has not confirmed" in flat
    assert "METFORMINA DELTA 850" in text and "1/2" in text
    assert "Sources consulted" in flat and "consulted on 2026-10-26" in flat
    assert "not a full interaction check" in flat


def test_pdf_never_says_the_plan_is_safe(tmp_path):
    text = pdf_text(tmp_path).lower()
    for phrase in ("this plan is safe", "safe plan", "no interactions", "no interaction", "all clear", "approved"):
        assert phrase not in text
    assert "lorazepam" not in text.split("not included")[0].lower().split("plan date")[1]  # the expired pack is not in the table
