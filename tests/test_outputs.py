"""What leaves the app: the printed calendar (read back from the PDF), the voice, and a saved plan."""

import wave
from datetime import date, timedelta

import pypdfium2 as pdfium
import pytest
from fixtures import (
    ACENOCUMAROL,
    IBUPROFENO,
    LORAZEPAM,
    METFORMINA_850,
    OMEPRAZOL,
    TODAY,
    FakeSmpc,
    pack,
)

from medtable import saved, voice
from medtable.calendar_pdf import render_pdf
from medtable.pillbox_pdf import render_pillbox
from medtable.form import Row
from medtable.plan import Entry, build_plan
from medtable.rules import check_packs, meal_notes
from medtable.schedule import SLOTS, Line, reconcile


def line(text, remarks="", confirmed=True, **doses):
    return Line(text, {**dict.fromkeys(SLOTS, "0"), **doses}, remarks, confirmed=confirmed)


def pages(path):
    doc = pdfium.PdfDocument(str(path))
    return [" ".join(doc[i].get_textpage().get_text_range().split()) for i in range(len(doc))]


def test_the_calendar_shows_the_confirmed_doses_the_safeguards_and_what_was_left_out(tmp_path):
    lines = [line("Metformina 850 mg", "con las comidas", breakfast="1", dinner="1/2"), line("Lorazepam 1 mg", bedtime="1"),
             line("Omeprazol 20 mg", breakfast="1", confirmed=False)]
    packs = [pack(METFORMINA_850), pack(LORAZEPAM, TODAY - timedelta(days=2)), pack(IBUPROFENO), pack(ACENOCUMAROL), pack(OMEPRAZOL)]
    recon = reconcile(lines, packs)
    plan = build_plan(lines, recon, check_packs(packs, FakeSmpc(), TODAY) + meal_notes(packs, FakeSmpc()) + recon.findings, TODAY)
    front, *rest = pages(render_pdf(plan, tmp_path / "plan.pdf", "Maria Lopez", notes="Dr Vega 981 000 000", times={"breakfast": "07:45"}))
    assert "For: Maria Lopez" in front and "07:45" in front and "Dr Vega 981 000 000" in front and "con las comidas" in front
    back = " ".join(rest)
    assert "METFORMINA DELTA 850" in front and "1/2" in front and "LORAZEPAM" not in front.split("Date:")[1]       # the expired box is not on the fridge page
    assert "are NOT in this calendar" in front and "Not included in the calendar" in back and "expired" in back and "has not confirmed" in back
    text = (front + back).lower()
    assert "does not replace the doctor or the pharmacist" in text and "not a full interaction check" in text and "consulted on 2026-10-26" in text
    assert not any(p in text for p in ("this plan is safe", "safe plan", "no interactions", "no interaction", "all clear", "approved"))


def test_two_doses_of_one_pack_at_the_same_time_are_both_printed(tmp_path):
    box = pack(METFORMINA_850, date(2030, 1, 1))
    plan = build_plan([], reconcile([], []), [], TODAY)
    plan.entries = [Entry("breakfast", box, line("A", breakfast="1"), "1"), Entry("breakfast", box, line("B", breakfast="2"), "2")]
    front = pages(render_pdf(plan, tmp_path / "y.pdf"))[0]
    assert "1 tablet" in front and "2 tablets" in front


def test_the_pill_organiser_page_fills_each_compartment_only_on_the_chosen_days(tmp_path):
    weekly = line("Lorazepam 1 mg", bedtime="1/2")
    weekly.days = (0, 3)
    lines = [line("Metformina 850 mg", breakfast="1"), weekly, line("Omeprazol 20 mg", breakfast="1")]
    plan = build_plan(lines, reconcile(lines, [pack(METFORMINA_850), pack(LORAZEPAM), pack(OMEPRAZOL, TODAY - timedelta(days=1))]), [], TODAY)
    page, = pages(render_pillbox(plan, tmp_path / "box.pdf", "Maria Lopez"))
    assert page.count("METFORMINA DELTA 850 mg") == 7 and page.count("1/2 tablet LORAZEPAM") == 2 and "OMEPRAZOL" not in page     # the expired box stays out
    assert "1 item(s) are NOT on this page" in page and "does not replace the doctor" in page


@pytest.mark.skipif(not voice.available(), reason="no English Windows speech voice installed")
def test_the_voice_reads_each_time_of_day_with_medication(tmp_path):
    lines = [line("Metformina 850 mg", "con las comidas", breakfast="1", dinner="1/2"), line("Omeprazol 20 mg", breakfast="1")]
    plan = build_plan(lines, reconcile(lines, [pack(METFORMINA_850), pack(OMEPRAZOL)]), [], TODAY)
    files = voice.render_voice(plan, tmp_path)
    assert set(files) == {"breakfast", "dinner"}
    for path in files.values():
        with wave.open(str(path)) as w:
            assert w.getnframes() / w.getframerate() > 2


def test_a_saved_plan_keeps_the_choices_not_the_verdicts_and_refuses_other_files():
    row = Row("pack654177", "SINTROM 1 mg", "654177", {"breakfast": "1", "lunch": "0", "dinner": "1/2", "bedtime": "0"}, "", ["With food"], True, days=[0, 3])
    text = saved.dump(rows=[row], codes=["(01)08470006541777(17)281231"], typed_cns=[], patient="Maria", notes="", times={"breakfast": "07:15"},
                      removed_cns=set(), removed_raw=set(), today=date(2026, 10, 30))
    assert "verified" not in text and "base64" not in text                  # codes are checked again when it is opened; no photos inside
    data = saved.load(text)
    assert (data["rows"][0].doses["dinner"], data["rows"][0].days, data["rows"][0].rev, data["times"]) == ("1/2", [0, 3], 1, {"breakfast": "07:15"})
    for bad, why in [("not json", "could not be read"), ('{"app": "other"}', "not a plan saved by this tool"), ('{"app": "med-table", "version": 99}', "another version")]:
        with pytest.raises(ValueError, match=why):
            saved.load(bad)
