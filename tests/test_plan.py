"""Plan building, speech text and calendar file."""

from datetime import date, timedelta

from fixtures import LORAZEPAM, METFORMINA_850, OMEPRAZOL, PARACETAMOL_A, TODAY, pack
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


def test_a_medicine_taken_on_some_days_is_written_spoken_and_reminded_on_those_days_only():
    weekly = line("Lorazepam 1 mg", {"bedtime": "1"})
    weekly.days = (0, 3)                                                    # Monday and Thursday
    plan = make([weekly, line("Omeprazol 20 mg", {"breakfast": "1"})], [pack(LORAZEPAM), pack(OMEPRAZOL)])
    night = plan.slot_entries("bedtime")[0]
    assert night.days_text() == "Mon, Thu only" and plan.slot_entries("breakfast")[0].days_text() == ""
    assert "one tablet of LORAZEPAM ETA 1 mg COMPRIMIDOS, on Mondays and Thursdays only." in speech_text(plan, "bedtime")
    ics = to_ics(plan, start=date(2026, 10, 27))                            # a Tuesday
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO,TH" in ics and "DTSTART:20261029T230000" in ics      # first reminder on the Thursday
    assert "RRULE:FREQ=DAILY" in ics                                        # the daily one is unchanged


def test_a_line_with_no_day_chosen_is_left_out_not_taken_as_every_day():
    never = line("Lorazepam 1 mg", {"bedtime": "1"})
    never.days = ()
    plan = make([never], [pack(LORAZEPAM)])
    assert plan.entries == [] and plan.not_included == [("Lorazepam 1 mg", "no day of the week is chosen")]


def test_how_long_a_box_lasts_is_counted_from_the_pack_size_and_the_confirmed_doses():
    from medtable.plan import box_days, units_in_pack
    assert units_in_pack("SINTROM 1 mg COMPRIMIDOS , 60 comprimidos") == 60
    assert units_in_pack("OMEPRAZOL 20 mg CAPSULAS DURAS EFG, 28 cápsulas") == 28
    assert units_in_pack("IBUPROFENO 20 MG/ML SUSPENSION ORAL 1 frasco de 200 ml") is None      # not counted in doses
    daily = line("Sintrom", {"breakfast": "1", "dinner": "1/2"})
    assert box_days(60, daily) == 40
    weekly = line("Sintrom", {"breakfast": "1"})
    weekly.days = (0, 3)
    assert box_days(60, weekly) == 210                                      # 2 a week
    assert box_days(60, line("Sintrom", {"breakfast": "media"})) is None


def test_an_unusually_large_daily_amount_is_flagged_for_a_second_look_not_blocked():
    from medtable.plan import large_amount
    assert large_amount(line("A", {"breakfast": "3", "lunch": "3", "dinner": "2"})) == 8.0
    assert large_amount(line("A", {"breakfast": "10"})) == 10.0
    assert large_amount(line("A", {"breakfast": "2", "dinner": "2"})) is None
    plan = make([line("Omeprazol 20 mg", {"breakfast": "3", "lunch": "3", "dinner": "3"})], [pack(OMEPRAZOL)])
    assert len(plan.entries) == 3                                           # still the caregiver's decision
