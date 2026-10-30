"""Sheet reader: model replies become unconfirmed rows; nothing is invented or silently corrected."""

from medtable import sheet_reader
from medtable.pipeline import make_plan

GOOD = '''```json
[{"medicine": "Metformina 850 mg comprimidos", "breakfast": "1", "lunch": "", "dinner": "1", "bedtime": "0", "remarks": "con las comidas"},
 {"medicine": "Lorazepam 1 mg", "breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "½", "remarks": "solo si insomnio"}]
```'''


def test_rows_are_unconfirmed_and_cells_are_copied():
    reading = sheet_reader.rows_from_reply(GOOD)
    assert len(reading.problems) == 1 and "empty or unread cell in lunch" in reading.problems[0]  # the empty cell is reported, not silent
    assert [r["confirmed"] for r in reading.rows] == [False, False]
    assert reading.rows[0]["lunch"] == "0" and reading.rows[0]["remarks"] == "con las comidas"
    assert reading.rows[1]["bedtime"] == "1/2"  # only the typographic fraction is normalised
    assert sheet_reader.clean_dose("1½") == "1½"  # a mixed number is kept as read (and later rejected), never mangled into "11/2"


def test_unrecognised_dose_is_kept_and_reported_never_replaced_by_zero():
    bad = '[{"medicine": "Lorazepam 1 mg", "breakfast": "media", "lunch": "0", "dinner": "0", "bedtime": "1-2", "remarks": ""}]'
    reading = sheet_reader.rows_from_reply(bad)
    assert reading.rows[0]["breakfast"] == "media" and reading.rows[0]["bedtime"] == "1-2"
    assert len(reading.problems) == 2 and "\"media\"" in reading.problems[0]


def test_a_misread_dose_cannot_reach_the_calendar():
    from fixtures import LORAZEPAM, TODAY, FakeSmpc
    from medtable.identify import Reading
    rows = sheet_reader.rows_from_reply('[{"medicine": "Lorazepam 1 mg", "breakfast": "media", "lunch": "0", "dinner": "0", "bedtime": "0", "remarks": ""}]').rows
    rows[0]["confirmed"] = True  # even if the caregiver ticks it
    result = make_plan([Reading("verified", (0, 0, 1, 1), "zxing", "x", "7000010", LORAZEPAM)], [], rows, FakeSmpc(), TODAY)
    assert result.plan.entries == []
    assert any(f.kind == "invalid_dose" for f in result.plan.findings)
    assert "unrecognised dose" in result.plan.not_included[0][1]
