"""From the doctor's sheet to the plan: only what the caregiver confirmed for a verified, unexpired pack reaches the calendar; doubts are asked, never guessed."""

from datetime import date, timedelta

from fixtures import (
    IBUPROFENO,
    LORAZEPAM,
    METFORMINA_500,
    METFORMINA_850,
    OMEPRAZOL,
    PARACETAMOL_A,
    TODAY,
    VALSARTAN_HCT,
    FakeSmpc,
    med,
    pack,
    strength,
)

from medtable import sheet_reader
from medtable.changes import compare
from medtable.form import Row, merge_read_rows, sync_pack_rows
from medtable.identify import Reading
from medtable.pipeline import make_plan
from medtable.plan import (
    Entry,
    box_days,
    build_plan,
    large_amount,
    speech_text,
    to_ics,
    units_in_pack,
)
from medtable.schedule import SLOTS, Line, reconcile

LATER = date(2030, 1, 1)


def line(text, confirmed=True, days=None, **doses):
    found = Line(text, {**dict.fromkeys(SLOTS, "0"), **doses}, confirmed=confirmed)
    if days is not None:
        found.days = days
    return found


def plan_of(lines, packs):
    return build_plan(lines, reconcile(lines, packs), [], TODAY)


def row(text, confirmed=True, **doses):
    return {"medicine": text, **dict.fromkeys(SLOTS, "0"), "remarks": "", "confirmed": confirmed, **doses}


def reading(medicine, expiry=LATER):
    return Reading("verified", (0, 0, 1, 1), "zxing", "x" + medicine.cn, medicine.cn + "0", medicine, expiry)


def test_only_confirmed_lines_of_verified_packs_reach_the_plan():
    unverified = Reading("unverified", (0, 0, 1, 1), "zxing", "xyz", problems=["not a GS1 element string"])
    rows = [row("Omeprazol 20 mg", breakfast="1"), row("Metformina 850 mg", confirmed=False, breakfast="1"), row("Atorvastatina 20 mg", dinner="1")]
    result = make_plan([reading(OMEPRAZOL), reading(METFORMINA_850), unverified], [], rows, None, TODAY)
    assert [(e.slot, e.name) for e in result.plan.entries] == [("breakfast", OMEPRAZOL.name)]
    reasons = dict(result.plan.not_included)
    assert "has not confirmed" in reasons["Metformina 850 mg"] and reasons["Atorvastatina 20 mg"] == "no pack on the table matches"
    assert reasons["the code read is not a GS1 medicine code"] == "could not be verified"


def test_an_expired_box_never_enters_but_a_fresh_box_of_the_same_medicine_does():
    assert "expired" in plan_of([line("Omeprazol 20 mg", breakfast="1")], [pack(OMEPRAZOL, TODAY - timedelta(days=3))]).not_included[0][1]
    fresh, old = pack(OMEPRAZOL, TODAY + timedelta(days=200)), pack(OMEPRAZOL, TODAY - timedelta(days=3))
    for packs in ([fresh, old], [old, fresh]):
        plan = plan_of([line("Omeprazol 20 mg", breakfast="1")], packs)
        assert [e.name for e in plan.entries] == [OMEPRAZOL.name] and plan.not_included == []


def test_doubtful_lines_are_left_out_with_their_reason_never_guessed():
    def reason(lines, packs):
        plan = plan_of(lines, packs)
        assert plan.entries == []
        return plan.not_included[0][1]
    assert reason([line("Metformina", breakfast="1")], [pack(METFORMINA_850), pack(METFORMINA_500)]) == "several packs match; say which one"
    assert reason([line("Metformina 500 mg", breakfast="1")], [pack(METFORMINA_850)]) == "the strength on the sheet does not match the pack"
    assert reason([line("Metformina 850 mg", breakfast="1"), line("Metformina 850 mg", breakfast="1")], [pack(METFORMINA_850)]) == "the pack is on several lines; keep one"
    assert reason([line("Metformina 850 mg")], [pack(METFORMINA_850)]) == "the line has no dose"
    assert reason([line("Lorazepam 1 mg", days=(), bedtime="1")], [pack(LORAZEPAM)]) == "no day of the week is chosen"         # not "every day"
    assert reason([line("Lorazepam 1 mg", breakfast="media")], [pack(LORAZEPAM)]) == "unrecognised dose: media"
    assert reason([line("Valsartan", breakfast="1")], [pack(VALSARTAN_HCT)]) == "no pack on the table matches"             # one ingredient of a combination is not it
    assert reconcile([Line("el de la mañana", cn="6800027")], [pack(METFORMINA_850), pack(METFORMINA_500)]).matches[0].medicine.cn == "680002"
    syrup = med("720001", "IBUPROFENO 20 MG/ML SUSPENSION ORAL", ["IBUPROFENO"], "M01AE01", strengths=strength(("2.0", "g")), form="SUSPENSION ORAL")
    salt = med("653397", "AMLODIPINO CINFA 5 mg COMPRIMIDOS EFG", ["AMLODIPINO BESILATO"], "C08CA01", strengths=strength(("6,94", "mg")))
    micro = med("698095", "EUTIROX 100 microgramos COMPRIMIDOS", ["LEVOTIROXINA SODICA"], "H03AA01", strengths=strength(("100", "\u00b5g")))
    for medicine, right, wrong in ((salt, "Amlodipino 5 mg", "Amlodipino 10 mg"), (micro, "Eutirox 100 microgramos", "Eutirox 50 microgramos")):
        assert reconcile([Line(medicine.name)], [pack(medicine)]).blocked == {} and reconcile([Line(right)], [pack(medicine)]).blocked == {}     # the name on the box is the strength
        assert reconcile([Line(wrong)], [pack(medicine)]).blocked == {0: "the strength on the sheet does not match the pack"}
    assert reconcile([Line("Ibuprofeno 20 mg/ml")], [pack(syrup)]).blocked == {}        # CIMA gives liquids per container: not compared


def test_the_dose_is_written_spoken_and_reminded_exactly_as_confirmed_on_its_days():
    assert Entry("bedtime", pack(LORAZEPAM), line("L", bedtime="1/2"), "1/2").written() == "1/2 tablet"
    assert Entry("breakfast", pack(OMEPRAZOL), line("O", breakfast="2"), "2").written() == "2 capsules"
    weekly = line("Lorazepam 1 mg", days=(0, 3), bedtime="1/2")
    plan = plan_of([weekly, line("Paracetamol 1 g", breakfast="2")], [pack(LORAZEPAM), pack(PARACETAMOL_A)])
    assert plan.slot_entries("bedtime")[0].days_text() == "Mon, Thu only"
    assert "half a tablet of LORAZEPAM ETA 1 mg COMPRIMIDOS, on Mondays and Thursdays only." in speech_text(plan, "bedtime")
    assert "two tablets of PARACETAMOL" in speech_text(plan, "breakfast") and speech_text(plan, "lunch") == "Lunch: nothing in the plan."
    ics = to_ics(plan, start=date(2026, 10, 27))                            # a Tuesday
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO,TH" in ics and "DTSTART:20261029T230000" in ics and "RRULE:FREQ=DAILY" in ics


def test_how_long_a_box_lasts_and_a_second_look_at_large_amounts_that_are_not_blocked():
    assert units_in_pack("SINTROM 1 mg COMPRIMIDOS , 60 comprimidos") == 60 and units_in_pack("IBUPROFENO 20 MG/ML 1 frasco de 200 ml") is None
    assert box_days(60, line("S", breakfast="1", dinner="1/2")) == 40 and box_days(60, line("S", days=(0, 3), breakfast="1")) == 210
    assert large_amount(line("A", breakfast="3", lunch="3", dinner="2")) == 8.0 and large_amount(line("A", breakfast="2", dinner="2")) is None
    assert len(plan_of([line("Omeprazol 20 mg", breakfast="3", lunch="3", dinner="3")], [pack(OMEPRAZOL)]).entries) == 3     # the caregiver decides


def test_the_tool_never_fills_or_confirms_a_dose_by_itself():
    rows = []
    assert len(sync_pack_rows(rows, [METFORMINA_850, METFORMINA_850, LORAZEPAM])) == 2
    assert all(r.untouched and not r.confirmed for r in rows)               # one empty row per pack, nothing proposed
    read = sheet_reader.rows_from_reply('[{"medicine": "Metformina 850 mg", "breakfast": "1", "lunch": "", "dinner": "media", "bedtime": "\u00bd"}]')
    assert read.rows[0]["confirmed"] is False and read.rows[0]["lunch"] == "0" and read.rows[0]["dinner"] == "media" and read.rows[0]["bedtime"] == "1/2"
    assert len(read.problems) == 2                                          # the empty cell and the unreadable "media" are reported, never silent
    merge_read_rows(rows, read.rows, [pack(METFORMINA_850), pack(LORAZEPAM)])
    assert rows[0].doses["breakfast"] == "1" and not rows[0].confirmed      # it fills the pack's untouched row, unconfirmed
    rows[1].doses["bedtime"] = "2"
    merge_read_rows(rows, [{"medicine": "Lorazepam 1 mg", "bedtime": "1"}], [pack(LORAZEPAM)])
    assert rows[1].doses["bedtime"] == "2" and len(rows) == 3               # what the caregiver chose is never overwritten


def test_a_reopened_plan_shows_every_change_since_it_was_saved():
    saved = [Row("pack680001", "METFORMINA 850", "680001", {"breakfast": "1", "lunch": "0", "dinner": "1", "bedtime": "0"}, confirmed=True),
             Row("pack700001", "LORAZEPAM 1 mg", "700001", {"breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "1"}, confirmed=True)]
    now = [Row("pack680001", "METFORMINA 850", "680001", {"breakfast": "1", "lunch": "0", "dinner": "1/2", "bedtime": "0"}, days=[0, 3]),
           Row("pack690001", "OMEPRAZOL 20 mg", "690001"), Row("pack700001", "LORAZEPAM 1 mg", "700001", {"breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "1"})]
    assert compare(saved, saved, None).__bool__() is False
    found = compare(saved, now, None)                                       # no new photo yet: nothing is called "not seen"
    assert found.new == ["OMEPRAZOL 20 mg"] and found.not_seen == []
    assert found.amounts == [("METFORMINA 850", ["Dinner: 1 -> \u00bd", "Days: every day -> Mon, Thu"])]
    assert compare(saved, now, {"680001", "690001"}).not_seen == ["LORAZEPAM 1 mg"]


def test_end_to_end_with_findings():
    readings = [reading(METFORMINA_850), reading(IBUPROFENO), reading(OMEPRAZOL, TODAY - timedelta(days=1))]
    rows = [row("Metformina 850 mg", breakfast="1", dinner="1"), row("Omeprazol 20 mg", breakfast="1"), row("Ibuprofeno 600 mg", confirmed=False, lunch="1")]
    result = make_plan(readings, [], rows, FakeSmpc(), TODAY)
    assert [(e.slot, e.pack.medicine.cn) for e in result.plan.entries] == [("breakfast", "680001"), ("dinner", "680001")]
    assert {"expired", "meal_note"} <= {f.kind for f in result.plan.findings}
