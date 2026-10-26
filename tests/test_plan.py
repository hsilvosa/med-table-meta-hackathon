"""Plan building, speech text and calendar file."""

from datetime import date, timedelta

from fixtures import LORAZEPAM, METFORMINA_850, OMEPRAZOL, PARACETAMOL_A, TODAY, pack
from medtable.findings import Finding
from medtable.plan import Entry, build_plan, speech_text, to_ics
from medtable.schedule import Line, reconcile


def make(lines, packs, findings=None):
    return build_plan(lines, reconcile(lines, packs), findings or [], TODAY)


def line(text, doses, remarks="", confirmed=True):
    return Line(text, {**{"desayuno": "0", "comida": "0", "cena": "0", "acostarse": "0"}, **doses}, remarks, confirmed=confirmed)


def test_only_confirmed_matched_lines_reach_the_plan():
    lines = [line("Omeprazol 20 mg", {"desayuno": "1"}), line("Metformina 850 mg", {"desayuno": "1", "cena": "1"}, confirmed=False),
             line("Atorvastatina 20 mg", {"cena": "1"})]
    plan = make(lines, [pack(OMEPRAZOL), pack(METFORMINA_850)])
    assert [(e.slot, e.name) for e in plan.entries] == [("desayuno", OMEPRAZOL.name)]
    reasons = dict(plan.not_included)
    assert "no ha sido confirmada" in reasons["Metformina 850 mg"]
    assert reasons["Atorvastatina 20 mg"] == "no hay ningún envase en la mesa"


def test_an_expired_pack_never_enters_the_calendar():
    plan = make([line("Omeprazol 20 mg", {"desayuno": "1"})], [pack(OMEPRAZOL, TODAY - timedelta(days=3))])
    assert plan.entries == [] and "caducó" in plan.not_included[0][1]


def test_unverified_items_are_listed_as_not_included():
    plan = make([], [], [Finding("unverified_item", detail="CIMA has no medicine with CN 123456")])
    assert plan.not_included == [("CIMA has no medicine with CN 123456", "no se pudo verificar")]


def test_dose_is_written_exactly_as_confirmed():
    half = Entry("acostarse", pack(LORAZEPAM), line("Lorazepam", {"acostarse": "1/2"}), "1/2")
    two = Entry("desayuno", pack(PARACETAMOL_A), line("Paracetamol", {"desayuno": "2"}), "2")
    one = Entry("desayuno", pack(PARACETAMOL_A), line("Paracetamol", {"desayuno": "1"}), "1")
    comma = Entry("desayuno", pack(PARACETAMOL_A), line("Paracetamol", {"desayuno": "0,5"}), "0,5")
    assert (half.written(), two.written(), one.written(), comma.written()) == ("1/2 comprimido", "2 comprimidos", "1 comprimido", "0,5 comprimido")
    assert OMEPRAZOL.form == "CAPSULAS DURAS"
    assert Entry("desayuno", pack(OMEPRAZOL), line("Omeprazol", {"desayuno": "2"}), "2").written() == "2 cápsulas"


def test_speech_reads_fractions_and_abbreviations_correctly():
    lines = [line("Lorazepam 1 mg", {"acostarse": "1/2"}, "solo si insomnio"), line("Paracetamol 1 g", {"acostarse": "0,5", "desayuno": "2"}, "cada 8 h si dolor, 500 mg")]
    plan = make(lines, [pack(LORAZEPAM), pack(PARACETAMOL_A)])
    night = speech_text(plan, "acostarse")
    assert "medio comprimido de LORAZEPAM ETA 1 mg COMPRIMIDOS. solo si insomnio." in night
    assert "medio comprimido de PARACETAMOL ALFA" in night and "cada 8 horas si dolor, 500 miligramos." in night
    assert "dos comprimidos de PARACETAMOL" in speech_text(plan, "desayuno")
    assert speech_text(plan, "comida") == "Comida: no hay medicación en el plan."


def test_ics_has_one_daily_reminder_per_slot_with_medication():
    lines = [line("Omeprazol 20 mg", {"desayuno": "1"}), line("Metformina 850 mg", {"desayuno": "1", "cena": "1"}, "con las comidas; sin falta")]
    plan = make(lines, [pack(OMEPRAZOL), pack(METFORMINA_850)])
    ics = to_ics(plan, {"cena": "20:45"}, start=date(2026, 10, 27), days=30)
    assert ics.count("BEGIN:VEVENT") == 2 and ics.count("BEGIN:VALARM") == 2
    assert "DTSTART:20261027T083000" in ics and "DTSTART:20261027T204500" in ics
    assert "RRULE:FREQ=DAILY;COUNT=30" in ics
    assert "con las comidas\\; sin falta" in ics  # semicolons are escaped
    assert ics.startswith("BEGIN:VCALENDAR") and ics.endswith("END:VCALENDAR\r\n")


def test_spoken_gender_agrees_with_the_unit():
    caps = lambda d: Entry("desayuno", pack(OMEPRAZOL), line("Omeprazol", {"desayuno": d}), d).spoken()
    assert (caps("1"), caps("2"), caps("1/2")) == ("una cápsula", "dos cápsulas", "media cápsula")
