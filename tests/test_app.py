"""The Streamlit app, driven headless with AppTest. No network: CIMA and the SmPC client are replaced."""

import os

import pytest
from streamlit.testing.v1 import AppTest

from fixtures import med
from medtable.resolve import Resolver
from medtable.smpc import Smpc

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")
MEDS = {cn: med(cn, f"MEDICAMENTO {cn} 10 mg COMPRIMIDOS", [f"INGREDIENTE{cn}"], f"N{cn[:2]}AA{cn[-2:]}")
        for cn in ("654177", "662025", "715240", "677379", "656012")}


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: MEDS.get("".join(c for c in cn if c.isdigit())[:6]))
    monkeypatch.setattr(Smpc, "section", lambda self, nregistro, section: None)
    monkeypatch.setenv("VLM_BACKEND", "meta")
    monkeypatch.chdir(tmp_path)
    return AppTest.from_file(APP, default_timeout=120).run()


def click(at, label):
    [b for b in at.button if b.label.startswith(label)][0].click()
    return at.run()


def texts(at):
    return " ".join(m.value for m in at.markdown)


def widget(items, kind, row_id, slot=""):
    """The widget of a row, found by kind, row id and slot whatever the row's revision is (the key is kind_rowid_rev[_slot])."""
    found = [w for w in items if w.key.startswith(f"{kind}_{row_id}_") and (w.key.endswith(f"_{slot}") if slot else w.key.count("_") == 2)]
    assert len(found) == 1, (kind, row_id, slot, [w.key for w in items][:6])
    return found[0]


def pick(at, row_id, slot, value):
    widget(at.button_group, "dose", row_id, slot).set_value(value)
    return at.run()


def doses_of(at):
    return [g for g in at.button_group if g.key.startswith("dose_")]


def confirm(at, row_id):
    widget(at.checkbox, "ok", row_id).check()
    return at.run()


def to_doses(at):
    click(at, "Load a demo photo")
    return click(at, "Next: choose the doses")


def test_starts_on_the_first_screen_with_the_disclaimer_and_a_disabled_next(app):
    assert not app.exception and app.session_state.step == 1
    assert any("does not replace the doctor or the pharmacist" in i.value for i in app.info)
    assert [b.disabled for b in app.button if b.label.startswith("Next:")] == [True]       # nothing to plan yet
    assert "Add at least one medicine to continue" in texts(app)


def test_demo_photo_gives_recognised_boxes_and_one_that_is_not_in_the_plan(app):
    click(app, "Load a demo photo")
    assert not app.exception
    readings = [r for rs in app.session_state.readings.values() for r in rs]
    assert sorted(r.status for r in readings) == ["unverified"] + ["verified"] * 5
    assert len(app.session_state.rows) == 5 and all(r.untouched for r in app.session_state.rows)      # nothing pre-filled
    shown = texts(app)
    assert "Medicines found: 5" in shown and "could not be recognised" in shown and "Not in the plan" in shown
    assert [b.disabled for b in app.button if b.label.startswith("Next:")] == [False]


def test_the_screens_follow_one_after_another_and_back(app):
    to_doses(app)
    assert app.session_state.step == 2 and "Choose the doses" in texts(app)
    assert len(doses_of(app)) == 5 * 4                                     # four times of day per medicine
    click(app, "Back")
    assert app.session_state.step == 1 and "Show me the medicines" in texts(app)


def test_every_dose_starts_at_none_and_nothing_reaches_the_plan_until_confirmed(app):
    to_doses(app)
    assert {g.value for g in doses_of(app)} == {"0"}                         # the app never proposes an amount
    pick(app, "pack654177", "breakfast", "1")
    click(app, "Next: see the plan")
    assert "Nothing in the plan yet" in texts(app)                           # chosen but not confirmed
    click(app, "Back")
    confirm(app, "pack654177")
    click(app, "Next: see the plan")
    agenda = [m.value for m in app.markdown if "mt-agenda" in m.value][-1]
    breakfast, rest = agenda.split("Lunch")[0], agenda.split("Lunch")[1]
    assert "1 tablet" in breakfast and "MEDICAMENTO 654177" in breakfast and "MEDICAMENTO 654177" not in rest


def test_other_amount_shows_a_text_box_and_a_bad_amount_is_reported_not_guessed(app):
    to_doses(app)
    pick(app, "pack654177", "dinner", "other")
    widget(app.text_input, "other", "pack654177", "dinner").set_value("media").run()
    pick(app, "pack654177", "breakfast", "1")
    confirm(app, "pack654177")
    click(app, "Next: see the plan")
    shown = texts(app)
    assert "Left out: MEDICAMENTO 654177" in shown and "unrecognised dose" in shown.lower()


def test_a_pack_on_two_lines_is_blocked_on_the_check_screen(app):
    to_doses(app)
    pick(app, "pack654177", "breakfast", "1")
    confirm(app, "pack654177")
    app.session_state.rows.append(type(app.session_state.rows[0])("hand9", app.session_state.rows[0].medicine, app.session_state.rows[0].cn,
                                  {"breakfast": "0", "lunch": "1", "dinner": "0", "bedtime": "0"}, confirmed=True))
    app.run()
    click(app, "Next: see the plan")
    assert "Pack on several lines" in texts(app) or "several lines" in texts(app)
    assert any("could not be checked" in m.value for m in app.markdown) or any("could not be checked" in c.value for c in app.caption)


def test_the_meta_backend_asks_for_consent_before_the_schedule_photo_leaves(app):
    to_doses(app)
    assert any("LEAVES this computer" in w.value for w in app.warning)
    assert [c.label for c in app.checkbox if c.key == "sheet_consent"] == ["I understand where the picture is sent and want the computer to read it"]


def test_the_room_photo_can_be_the_schedule_but_only_after_consent(app, tmp_path):
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    (tmp_path / "data" / "world_photos" / "latest.jpg").write_bytes(b"x")
    at = AppTest.from_file(APP, default_timeout=120).run()
    to_doses(at)
    assert [b.disabled for b in at.button if b.label.startswith("Read the latest room photo")] == [True]
    [c for c in at.checkbox if c.key == "sheet_consent"][0].check()
    at.run()
    assert [b.disabled for b in at.button if b.label.startswith("Read the latest room photo")] == [False]


def test_a_schedule_read_from_a_photo_fills_the_dose_buttons_of_the_boxes_and_confirms_nothing(app, tmp_path, monkeypatch):
    from medtable import sheet_reader
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    (tmp_path / "data" / "world_photos" / "latest.jpg").write_bytes(b"x")
    rows = [{"medicine": "Enalapril 10 mg comprimidos", "breakfast": "1", "lunch": "0", "dinner": "1/2", "bedtime": "0", "remarks": "con comida", "confirmed": False},
            {"medicine": "Atorvastatina 20 mg", "breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "1", "remarks": "", "confirmed": False}]
    monkeypatch.setattr(sheet_reader, "read_sheet", lambda path, backend=None: sheet_reader.SheetReading(rows, [], "meta", 0.0))
    named = {**MEDS, "654177": med("654177", "ENALAPRIL TESTLAB 10 mg COMPRIMIDOS", ["ENALAPRIL"], "C09AA02")}      # a name the sheet line can match unambiguously
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: named.get("".join(c for c in cn if c.isdigit())[:6]))
    at = AppTest.from_file(APP, default_timeout=120).run()
    to_doses(at)
    [c for c in at.checkbox if c.key == "sheet_consent"][0].check()
    at.run()
    click(at, "Read the latest room photo")
    assert not at.exception
    assert [g.value for g in doses_of(at) if g.key.startswith("dose_pack654177_")] == ["1", "0", "1/2", "0"]     # the buttons SHOW what was read
    assert at.session_state.rows[0].remarks == "con comida" and not any(r.confirmed for r in at.session_state.rows)
    assert [g.value for g in doses_of(at) if g.key.startswith("dose_sheet")] == ["0", "0", "0", "1"]           # a line with no box becomes its own row


def test_the_last_screen_offers_the_downloads_only_when_there_is_a_plan(app):
    to_doses(app)
    click(app, "Next: see the plan")
    assert "Nothing in the plan yet" in texts(app)
    click(app, "Back")
    pick(app, "pack654177", "lunch", "2")
    confirm(app, "pack654177")
    click(app, "Next: see the plan")
    click(app, "Next: print or listen")
    assert app.session_state.step == 4 and not app.exception
    assert {el.proto.label for el in app.get("download_button")} == {"Download the calendar to print (PDF)", "Download the phone reminders (.ics)"}


def test_the_name_and_notes_can_be_given_on_the_doses_screen_and_again_before_printing(app):
    to_doses(app)
    [t for t in app.text_input if t.key == "patient_step2"][0].set_value("Maria Lopez").run()
    assert app.session_state.patient == "Maria Lopez"
    widget(app.button_group, "quick", "pack654177").set_value(["With food", "Only if needed"]).run()
    widget(app.text_input, "remarks", "pack654177").set_value("white tablet").run()
    assert app.session_state.rows[0].note == "With food; Only if needed; white tablet"
    pick(app, "pack654177", "breakfast", "1")
    confirm(app, "pack654177")
    click(app, "Next: see the plan")
    assert "Plan for <b>Maria Lopez</b>" in texts(app) and "With food; Only if needed; white tablet" in texts(app)
    click(app, "Next: print or listen")
    assert [t.value for t in app.text_input if t.key == "patient_step4"] == ["Maria Lopez"]       # the same value, editable again
    [t for t in app.text_input if t.key == "patient_step4"][0].set_value("Maria L.").run()
    [a for a in app.text_area if a.key == "plan_notes_box"][0].set_value("Dr Vega 981 000 000").run()
    assert app.session_state.patient == "Maria L." and app.session_state.plan_notes == "Dr Vega 981 000 000" and not app.exception
    assert "This is the page you will print" in texts(app)


def test_photos_survive_going_forward_and_back_and_can_be_removed_on_purpose(app):
    click(app, "Load a demo photo")
    readings = app.session_state.readings.pop("demo")          # pretend they came from an uploaded file: the uploader itself is empty in this test
    photo = app.session_state.photos.pop("demo")
    app.session_state.readings["table1.jpg"], app.session_state.photos["table1.jpg"] = readings, photo
    app.session_state.photo_scale["table1.jpg"] = 1.0
    app.run()
    assert "table1.jpg" in app.session_state.readings          # an empty uploader is not a removal
    click(app, "Next: choose the doses")
    click(app, "Back")
    app.run()
    assert "table1.jpg" in app.session_state.readings and "Medicines found: 5" in texts(app)
    click(app, "Remove")
    assert not app.session_state.readings and "Medicines found: 0" in texts(app)


def test_a_schedule_line_without_a_box_can_be_added_by_hand(app):
    to_doses(app)
    [t for t in app.text_input if t.key == "extra_name"][0].set_value("Bisoprolol 2,5 mg").run()
    click(app, "Add this line")
    assert not app.exception
    assert [r.medicine for r in app.session_state.rows][-1] == "Bisoprolol 2,5 mg" and app.session_state.rows[-1].cn is None
    assert [t.value for t in app.text_input if t.key == "extra_name"] == [""]               # the box is cleared for the next one
    pick(app, "hand6", "breakfast", "1")
    confirm(app, "hand6")
    click(app, "Next: see the plan")
    assert "Left out: Bisoprolol 2,5 mg" in texts(app) and "add a photo that shows this box" in texts(app)     # and the card says what to do


def test_a_48_megapixel_photo_is_read_in_full_but_only_a_smaller_copy_is_kept(app, tmp_path):
    import cv2
    import numpy as np
    from medtable import synthetic
    small = synthetic.demo_photo([("654177", "281231"), ("662025", "270430")])
    big = cv2.resize(small, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)        # 8000 x 5000: every code is five times wider in pixels
    assert big.shape[1] == 8000
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "data" / "world_photos" / "latest.jpg"), big)
    at = AppTest.from_file(APP, default_timeout=180).run()
    click(at, "Load the latest room photo")
    assert not at.exception
    name = next(iter(at.session_state.readings))
    assert sorted(r.status for r in at.session_state.readings[name]) == ["verified", "verified"]
    kept = at.session_state.photos[name]
    assert kept.shape[1] == 4000 and at.session_state.photo_scale[name] == 0.5                 # 8000 px wide in, 4000 kept


def test_start_over_clears_everything(app):
    to_doses(app)
    click(app, "Start over")
    assert app.session_state.step == 1 and not app.session_state.rows and not app.session_state.readings and not app.exception


def test_the_latest_photo_of_the_3d_room_can_be_loaded(app, tmp_path):
    import cv2
    from medtable import synthetic
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "data" / "world_photos" / "latest.jpg"), synthetic.demo_photo([("654177", "281231"), ("662025", "270430")]))
    at = AppTest.from_file(APP, default_timeout=120).run()
    click(at, "Load the latest room photo")
    assert not at.exception
    readings = [r for rs in at.session_state.readings.values() for r in rs]
    assert sorted(r.status for r in readings) == ["verified", "verified"]
    assert all(n.startswith("room_") for n in at.session_state.readings)
