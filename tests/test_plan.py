"""Plan building, speech text and calendar file."""

from datetime import date, timedelta

from fixtures import LORAZEPAM, METFORMINA_850, OMEPRAZOL, PARACETAMOL_A, TODAY, pack
from medtable.findings import Finding
from medtable.plan import Entry, build_plan, speech_text, to_ics
from medtable.schedule import Line, reconcile


def make(lines, packs, findings=None):
    return build_plan(lines, reconcile(lines, packs), findings or [], TODAY)


def line(text, doses, remarks="", confirmed=True):
    return Line(text, {**{"breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "0"}, **doses}, remarks, confirmed=confirmed)


def test_only_confirmed_matched_lines_reach_the_plan():
    lines = [line("Omeprazol 20 mg", {"breakfast": "1"}), line("Metformina 850 mg", {"breakfast": "1", "dinner": "1"}, confirmed=False),
             line("Atorvastatina 20 mg", {"dinner": "1"})]
    plan = make(lines, [pack(OMEPRAZOL), pack(METFORMINA_850)])
    assert [(e.slot, e.name) for e in plan.entries] == [("breakfast", OMEPRAZOL.name)]
    reasons = dict(plan.not_included)
    assert "has not confirmed" in reasons["Metformina 850 mg"]
    assert reasons["Atorvastatina 20 mg"] == "no pack on the table matches"


def test_an_expired_pack_never_enters_the_calendar():
    plan = make([line("Omeprazol 20 mg", {"breakfast": "1"})], [pack(OMEPRAZOL, TODAY - timedelta(days=3))])
    assert plan.entries == [] and "expired" in plan.not_included[0][1]


def test_two_boxes_of_one_medicine_use_the_one_that_has_not_expired_whatever_their_order():
    fresh, old = pack(OMEPRAZOL, TODAY + timedelta(days=200)), pack(OMEPRAZOL, TODAY - timedelta(days=3))
    for packs in ([fresh, old], [old, fresh]):
        plan = make([line("Omeprazol 20 mg", {"breakfast": "1"})], packs)
        assert [e.name for e in plan.entries] == [OMEPRAZOL.name] and plan.not_included == []


def test_unverified_items_are_listed_as_not_included():
    plan = make([], [], [Finding("unverified_item", detail="CIMA has no medicine with CN 123456")])
    assert plan.not_included == [("CIMA has no medicine with CN 123456", "could not be verified")]


def test_dose_is_written_exactly_as_confirmed():
    half = Entry("bedtime", pack(LORAZEPAM), line("Lorazepam", {"bedtime": "1/2"}), "1/2")
    two = Entry("breakfast", pack(PARACETAMOL_A), line("Paracetamol", {"breakfast": "2"}), "2")
    one = Entry("breakfast", pack(PARACETAMOL_A), line("Paracetamol", {"breakfast": "1"}), "1")
    comma = Entry("breakfast", pack(PARACETAMOL_A), line("Paracetamol", {"breakfast": "0,5"}), "0,5")
    assert (half.written(), two.written(), one.written(), comma.written()) == ("1/2 tablet", "2 tablets", "1 tablet", "0,5 tablet")
    assert OMEPRAZOL.form == "CAPSULAS DURAS"
    assert Entry("breakfast", pack(OMEPRAZOL), line("Omeprazol", {"breakfast": "2"}), "2").written() == "2 capsules"


def test_speech_reads_fractions_and_abbreviations_correctly():
    lines = [line("Lorazepam 1 mg", {"bedtime": "1/2"}, "only if insomnia"), line("Paracetamol 1 g", {"bedtime": "0,5", "breakfast": "2"}, "every 8 h if pain, 500 mg")]
    plan = make(lines, [pack(LORAZEPAM), pack(PARACETAMOL_A)])
    night = speech_text(plan, "bedtime")
    assert "half a tablet of LORAZEPAM ETA 1 mg COMPRIMIDOS. only if insomnia." in night
    assert "half a tablet of PARACETAMOL ALFA" in night and "every 8 hours if pain, 500 milligrams." in night
    assert "two tablets of PARACETAMOL" in speech_text(plan, "breakfast")
    assert speech_text(plan, "lunch") == "Lunch: nothing in the plan."


def test_ics_has_one_daily_reminder_per_slot_with_medication():
    lines = [line("Omeprazol 20 mg", {"breakfast": "1"}), line("Metformina 850 mg", {"breakfast": "1", "dinner": "1"}, "con las comidas; sin falta")]
    plan = make(lines, [pack(OMEPRAZOL), pack(METFORMINA_850)])
    ics = to_ics(plan, {"dinner": "20:45"}, start=date(2026, 10, 27), days=30)
    assert ics.count("BEGIN:VEVENT") == 2 and ics.count("BEGIN:VALARM") == 2
    assert "DTSTART:20261027T083000" in ics and "DTSTART:20261027T204500" in ics
    assert "RRULE:FREQ=DAILY;COUNT=30" in ics
    assert "con las comidas\\; sin falta" in ics  # semicolons are escaped
    assert ics.startswith("BEGIN:VCALENDAR") and ics.endswith("END:VCALENDAR\r\n")


def test_spoken_dose_agrees_with_the_unit():
    caps = lambda d: Entry("breakfast", pack(OMEPRAZOL), line("Omeprazol", {"breakfast": d}), d).spoken()
    assert (caps("1"), caps("2"), caps("1/2")) == ("one capsule", "two capsules", "half a capsule")
