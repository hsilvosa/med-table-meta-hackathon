"""A saved plan: what is in the file, and that opening it trusts nothing but the caregiver's own choices."""

from datetime import date

import pytest

from medtable import saved
from medtable.form import Row


def plan_file(**over):
    row = Row("pack654177", "SINTROM 1 mg", "654177", {"breakfast": "1", "lunch": "0", "dinner": "1/2", "bedtime": "0"}, "white", ["With food"], True, days=[0, 3])
    values = dict(rows=[row], codes=["(01)08470006541777(17)281231(10)L0(21)SN0"], typed_cns=["6620250"], patient="Maria", notes="Dr Vega",
                  times={"breakfast": "07:15"}, removed_cns={"715240"}, removed_raw=set(), today=date(2026, 10, 30))
    values.update(over)
    return saved.dump(**values)


def test_a_saved_plan_opens_with_the_same_choices_and_new_widget_keys():
    data = saved.load(plan_file())
    row = data["rows"][0]
    assert (row.doses["dinner"], row.days, row.quick, row.confirmed, row.rev) == ("1/2", [0, 3], ["With food"], True, 1)
    assert data["codes"] == ["(01)08470006541777(17)281231(10)L0(21)SN0"] and data["typed_cns"] == ["6620250"]
    assert (data["patient"], data["notes"], data["times"], data["removed_cns"], data["saved"]) == ("Maria", "Dr Vega", {"breakfast": "07:15"}, {"715240"}, "2026-10-30")


def test_a_file_that_is_not_a_saved_plan_is_refused_with_a_plain_reason():
    for text, why in [("not json", "could not be read"), ('{"app": "other"}', "not a plan saved by this tool"),
                      ('{"app": "med-table", "version": 99}', "another version"), ('{"app": "med-table", "version": 1, "rows": [{"id": "x"}]}', "damaged")]:
        with pytest.raises(ValueError, match=why):
            saved.load(text)
