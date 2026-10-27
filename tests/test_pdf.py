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
    assert "lorazepam" not in text.split("For the pharmacist")[0].lower().split("date:")[1]  # the expired pack is not in the calendar page


def two_pages(tmp_path, **kwargs):
    lines = [line("Metformina 850 mg", "con las comidas", breakfast="1"), line("Lorazepam 1 mg", bedtime="1")]
    packs = [pack(METFORMINA_850), pack(LORAZEPAM, TODAY - timedelta(days=2))]
    plan = build_plan(lines, reconcile(lines, packs), [], TODAY)
    out = render_pdf(plan, tmp_path / "plan.pdf", **kwargs)
    doc = pdfium.PdfDocument(str(out))
    return [" ".join(doc[i].get_textpage().get_text_range().split()) for i in range(len(doc))]


def test_calendar_page_has_the_name_notes_and_times_the_caregiver_gave(tmp_path):
    pages = two_pages(tmp_path, patient="Maria Lopez", notes="Doctor: Dr Vega 981 000 000\nAllergic to penicillin", times={"breakfast": "07:45"})
    assert len(pages) == 2
    assert "For: Maria Lopez" in pages[0] and "07:45" in pages[0] and "14:00" in pages[0]            # the other times keep their defaults
    assert "Doctor: Dr Vega 981 000 000" in pages[0] and "Allergic to penicillin" in pages[0] and "Phone:" not in pages[0]
    assert "con las comidas" in pages[0] and "Plan for: Maria Lopez" in pages[1]


def test_without_a_name_or_notes_the_page_prints_lines_to_write_on(tmp_path):
    pages = two_pages(tmp_path)
    assert "For: ____" in pages[0] and "Doctor: ____" in pages[0] and "Pharmacy: ____" in pages[0]


def test_page_one_says_when_something_is_left_out_and_page_two_says_what(tmp_path):
    pages = two_pages(tmp_path)
    assert "item(s) are NOT in this calendar" in pages[0] and "See page 2" in pages[0]
    assert "Not included in the calendar" in pages[1] and "Lorazepam 1 mg" in pages[1] and "expired" in pages[1]
