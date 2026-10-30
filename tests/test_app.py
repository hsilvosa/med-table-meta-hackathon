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
def env(monkeypatch, tmp_path):
    """The invented medicines in place of CIMA, an empty working folder: for tests that make their own AppTest after preparing files."""
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: MEDS.get("".join(c for c in cn if c.isdigit())[:6]))
    monkeypatch.setattr(Smpc, "section", lambda self, nregistro, section: None)
    monkeypatch.setenv("VLM_BACKEND", "meta")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def app(env):
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
    assert "Medicines found: 5" in shown and "A box I could not recognise" in shown and "Not in the plan" in shown
    assert [b.disabled for b in app.button if b.label.startswith("Next:")] == [False]
    assert not any(app.session_state.nocode.values()) and "A box where I could not read a code" not in shown      # a plain grid of codes has no packs without one


def test_the_screens_follow_one_after_another_and_back_and_start_over_clears_everything(app):
    to_doses(app)
    assert app.session_state.step == 2 and "Choose the doses" in texts(app)
    assert len(doses_of(app)) == 5 * 4                                     # four times of day per medicine
    click(app, "Back")
    assert app.session_state.step == 1 and "Show me the medicines" in texts(app)
    click(app, "Next: choose the doses")
    click(app, "Start over")                                               # it asks first: a slip of the finger must not delete the plan
    assert app.session_state.step == 2 and app.session_state.rows and "Start over?" in texts(app)
    click(app, "No, keep my work")
    assert app.session_state.step == 2 and app.session_state.rows and "Start over?" not in texts(app)
    click(app, "Start over")
    click(app, "Yes, delete everything")
    assert app.session_state.step == 1 and not app.session_state.rows and not app.session_state.readings and not app.exception


def test_every_dose_starts_at_none_nothing_reaches_the_plan_until_confirmed_and_a_bad_amount_is_not_guessed(app):
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
    click(app, "Back")                                                       # a ticked medicine is a short summary with its amounts
    assert "Breakfast: <b>1 tablet</b>" in texts(app) and not [w for w in doses_of(app) if "pack654177" in w.key]
    click(app, "Change the amounts")                                         # an amount typed under "Other" that is not understood is reported, never guessed
    pick(app, "pack654177", "dinner", "other")
    widget(app.text_input, "other", "pack654177", "dinner").set_value("media").run()
    confirm(app, "pack654177")
    click(app, "Next: see the plan")
    assert "Left out: MEDICAMENTO 654177" in texts(app) and "unrecognised dose" in texts(app).lower()


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


def test_the_schedule_photo_leaves_the_computer_only_after_consent_and_the_room_photo_can_be_it(env, tmp_path):
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    (tmp_path / "data" / "world_photos" / "latest.jpg").write_bytes(b"x")
    at = AppTest.from_file(APP, default_timeout=120).run()
    to_doses(at)
    assert any("LEAVES this computer" in w.value for w in at.warning)
    assert [c.label for c in at.checkbox if c.key == "sheet_consent"] == ["I understand where the picture is sent and want the computer to read it"]
    assert [b.disabled for b in at.button if b.label.startswith("Read the latest room photo")] == [True]
    [c for c in at.checkbox if c.key == "sheet_consent"][0].check()
    at.run()
    assert [b.disabled for b in at.button if b.label.startswith("Read the latest room photo")] == [False]


def test_a_schedule_read_from_a_photo_fills_the_dose_buttons_of_the_boxes_and_confirms_nothing(env, tmp_path, monkeypatch):
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


def test_a_48_megapixel_photo_is_read_in_full_but_only_a_smaller_copy_is_kept(env, tmp_path):
    import cv2
    import numpy as np
    from medtable import synthetic
    small = synthetic.demo_photo([("654177", "281231"), ("662025", "270430")])
    big = cv2.resize(small, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)        # 4800 x 3000: wider than the 4000 px that are kept
    assert big.shape[1] == 4800
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "data" / "world_photos" / "latest.jpg"), big)
    at = AppTest.from_file(APP, default_timeout=180).run()
    click(at, "Load the latest room photo")
    assert not at.exception
    name = next(iter(at.session_state.readings))
    assert sorted(r.status for r in at.session_state.readings[name]) == ["verified", "verified"]
    kept = at.session_state.photos[name]
    assert name.startswith("room_") and kept.shape[1] == 4000 and round(at.session_state.photo_scale[name], 3) == 0.833        # 4800 px wide in, 4000 kept


def test_a_medicine_can_be_removed_and_leaves_the_list_the_rows_and_the_plan(app):
    click(app, "Load a demo photo")
    assert "Medicines found: 5" in texts(app) and len(app.session_state.rows) == 5
    click(app, "Remove this medicine")                                  # the first card
    assert not app.exception and "Medicines found: 4" in texts(app)
    assert len(app.session_state.rows) == 4 and len(app.session_state.removed_cns) == 1
    removed = next(iter(app.session_state.removed_cns))
    assert removed not in {r.cn for r in app.session_state.rows}
    click(app, "Next: choose the doses")
    assert len(doses_of(app)) == 4 * 4                                  # no buttons for the removed medicine
    click(app, "Back")
    assert "Medicines found: 4" in texts(app)                           # still gone after going back
    app.session_state.readings.pop("demo"), app.session_state.photos.pop("demo")
    click(app, "Load a demo photo")                                      # the same photo again: the box is on the table again
    assert removed not in app.session_state.removed_cns and "Medicines found: 5" in texts(app)


def test_a_typed_medicine_can_be_removed_and_an_unrecognised_box_dismissed(app):
    [t for t in app.text_input if t.label == "The code on the box"][0].set_value("6541777")      # typed, then the button (or Enter): one form
    click(app, "Add this medicine")
    assert "Medicines found: 1" in texts(app) and "Added" in texts(app)
    click(app, "Remove this medicine")
    assert "Medicines found: 0" in texts(app) and not app.session_state.manual and not app.session_state.rows
    click(app, "Load a demo photo")
    assert "A box I could not recognise" in texts(app)
    click(app, "Dismiss")
    assert "A box I could not recognise" not in texts(app) and not app.exception


def test_a_box_where_no_code_was_read_gets_a_card_asking_for_a_close_up(env, tmp_path):
    import cv2
    from test_boxes import scene
    img, _, _ = scene()                                                       # two packs on a table: one has a readable code, one has none; and a sheet of paper
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "data" / "world_photos" / "latest.jpg"), img)
    at = AppTest.from_file(APP, default_timeout=180).run()
    click(at, "Load the latest room photo")
    assert not at.exception and "Medicines found: 1" in texts(at)
    assert texts(at).count("A box where I could not read a code") == 1 and "close-up photo of this box" in texts(at)
    click(at, "Done: I added it or it is not a medicine")
    assert "A box where I could not read a code" not in texts(at) and len(at.session_state.nocode_done) == 1


def test_photos_from_the_camera_page_are_read_from_their_own_folder_with_their_own_words(env, tmp_path):
    from medtable import synthetic
    import cv2
    (tmp_path / "data" / "camera_photos").mkdir(parents=True)
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "data" / "camera_photos" / "latest.jpg"), synthetic.demo_photo([("654177", "281231")]))
    cv2.imwrite(str(tmp_path / "data" / "world_photos" / "latest.jpg"), synthetic.demo_photo([("662025", "270430"), ("715240", "250600")]))
    at = AppTest.from_file(APP, default_timeout=180)
    at.query_params["source"], at.query_params["room"] = "camera", "1"
    at.run()
    assert "Load the latest camera photo" in [b.label for b in at.button] and "Load the latest room photo" not in [b.label for b in at.button]
    assert "Take the photo with the camera" in texts(at)
    click(at, "Load the latest camera photo")
    assert not at.exception and "Medicines found: 1" in texts(at) and next(iter(at.session_state.readings)).startswith("camera_")


def test_two_boxes_of_one_medicine_are_one_card_and_the_plan_uses_the_box_that_has_not_expired(env):
    from medtable import identify, synthetic
    from medtable.resolve import Resolver as R
    at = AppTest.from_file(APP, default_timeout=120).run()
    image = synthetic.demo_photo([("654177", "291231"), ("654177", "200131"), ("662025", "291231")])     # one box of the first medicine expired in 2020
    at.session_state["readings"] = {"two": identify.identify(image, R())}
    at.run()
    assert not at.exception and "Medicines found: 2" in texts(at) and "2 boxes" in texts(at)
    assert "1 of 2 boxes have expired" in texts(at)
    click(at, "Next: choose the doses")
    pick(at, "pack654177", "breakfast", "1")
    confirm(at, "pack654177")
    click(at, "Next: see the plan")
    agenda = [m.value for m in at.markdown if "mt-agenda" in m.value][-1]
    assert "MEDICAMENTO 654177" in agenda and "Left out: MEDICAMENTO 654177" not in texts(at)


def test_a_removed_medicine_can_be_put_back_with_its_doses(app):
    to_doses(app)
    pick(app, "pack654177", "breakfast", "1")
    confirm(app, "pack654177")
    click(app, "Back")
    click(app, "Remove this medicine")
    assert "Medicines found: 4" in texts(app) and "Removed: MEDICAMENTO 654177" in texts(app)
    click(app, "Undo: put it back")
    row = next(r for r in app.session_state.rows if r.cn == "654177")
    assert "Medicines found: 5" in texts(app) and row.doses["breakfast"] == "1" and row.confirmed and "Undo" not in [b.label[:4] for b in app.button]


def test_changing_an_amount_after_ticking_needs_a_new_tick(app):
    to_doses(app)
    confirm(app, "pack654177")                                              # ticked first, amounts after: the tick no longer stands
    pick(app, "pack654177", "breakfast", "1")
    assert not next(r for r in app.session_state.rows if r.cn == "654177").confirmed
    confirm(app, "pack654177")
    assert "1 of 5 medicines ready for the plan" in [p.text for p in app.get("progress")][0]


def test_the_reminder_times_are_kept_when_going_back_and_shown_on_the_check_screen(app):
    from datetime import time as clock
    to_doses(app)
    pick(app, "pack654177", "breakfast", "1")
    confirm(app, "pack654177")
    click(app, "Next: see the plan")
    click(app, "Next: print or listen")
    app.time_input(key="t_breakfast").set_value(clock(7, 15)).run()
    click(app, "Back")
    assert "07:15" in [m.value for m in app.markdown if "mt-agenda" in m.value][-1]
    click(app, "Next: print or listen")
    assert app.time_input(key="t_breakfast").value == clock(7, 15)


def test_a_photo_says_what_was_read_and_an_expired_box_is_marked(app):
    click(app, "Load a demo photo")
    assert "Photo read" in texts(app) and "5 medicines recognised, 1 box I could not recognise" in texts(app)
    assert "This box has expired. Do not use it" in texts(app)            # the demo photo has one pack that expired in June 2025
