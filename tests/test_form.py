"""The caregiver's sheet rows: dose buttons, merging a sheet read from a photo, and the guarantees around it."""

from datetime import date

from fixtures import LORAZEPAM, METFORMINA_850, TODAY, pack
from medtable.form import CHOICE_VALUES, OTHER, Row, choice_for, merge_read_rows, row_for_pack, sync_pack_rows
from medtable.pipeline import make_plan
from medtable.schedule import dose_number

READ = {"medicine": "Metformina 850 mg comprimidos", "breakfast": "1", "lunch": "0", "dinner": "1", "bedtime": "0", "remarks": "con las comidas"}


def test_every_button_value_is_a_dose_the_schedule_understands():
    assert all(dose_number(v) is not None for v in CHOICE_VALUES)
    assert choice_for("1/2") == "1/2" and choice_for("4") == OTHER and choice_for("") == OTHER and choice_for("media") == OTHER


def test_new_pack_rows_start_empty_unconfirmed_and_only_once():
    rows: list[Row] = []
    assert len(sync_pack_rows(rows, [METFORMINA_850, METFORMINA_850, LORAZEPAM])) == 2
    assert sync_pack_rows(rows, [METFORMINA_850]) == []
    assert all(r.untouched and not r.has_dose and not r.confirmed for r in rows)  # the tool never proposes an amount


def test_a_sheet_read_from_a_photo_fills_the_row_of_its_pack_instead_of_duplicating_it():
    rows = [row_for_pack(METFORMINA_850)]
    changed, notes = merge_read_rows(rows, [READ], [pack(METFORMINA_850)])
    assert len(rows) == 1 and changed == rows and notes == []
    assert rows[0].doses == {"breakfast": "1", "lunch": "0", "dinner": "1", "bedtime": "0"} and rows[0].remarks == "con las comidas"
    assert rows[0].confirmed is False and rows[0].sheet_name == "Metformina 850 mg comprimidos"      # read, never confirmed


def test_a_row_the_caregiver_already_worked_on_is_not_overwritten():
    rows = [row_for_pack(METFORMINA_850)]
    rows[0].doses["bedtime"] = "2"
    merge_read_rows(rows, [READ], [pack(METFORMINA_850)])
    assert rows[0].doses["bedtime"] == "2" and len(rows) == 2           # the read line became its own row; the plan will flag the pack on two lines


def test_a_line_that_names_no_pack_becomes_its_own_row():
    rows = [row_for_pack(METFORMINA_850)]
    merge_read_rows(rows, [{**READ, "medicine": "Atorvastatina 20 mg"}], [pack(METFORMINA_850)])
    assert [r.cn for r in rows] == [METFORMINA_850.cn, None] and rows[0].untouched and rows[1].medicine == "Atorvastatina 20 mg"


def test_the_same_line_read_twice_is_added_once_and_reported():
    rows: list[Row] = []
    merge_read_rows(rows, [{**READ, "medicine": "Atorvastatina 20 mg"}], [])
    _, notes = merge_read_rows(rows, [{**READ, "medicine": "Atorvastatina 20 mg"}], [])
    assert len(rows) == 1 and "already in the list" in notes[0]


def test_rows_feed_the_plan_and_only_confirmed_rows_count():
    rows = [row_for_pack(METFORMINA_850), row_for_pack(LORAZEPAM)]
    merge_read_rows(rows, [READ], [pack(METFORMINA_850), pack(LORAZEPAM)])
    result = make_plan([], [pack(METFORMINA_850, date(2030, 1, 1)), pack(LORAZEPAM, date(2030, 1, 1))], [r.as_record() for r in rows], None, TODAY)
    assert result.plan.entries == []                                     # nothing confirmed yet
    rows[0].confirmed = True
    result = make_plan([], [pack(METFORMINA_850, date(2030, 1, 1)), pack(LORAZEPAM, date(2030, 1, 1))], [r.as_record() for r in rows], None, TODAY)
    assert [e.name for e in result.plan.entries] == [METFORMINA_850.name] * 2
