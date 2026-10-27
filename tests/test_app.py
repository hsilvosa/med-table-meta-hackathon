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


def pick(at, row_id, slot, value):
    [g for g in at.button_group if g.key == f"dose_{row_id}_{slot}"][0].set_value(value)
    return at.run()


def confirm(at, row_id):
    [c for c in at.checkbox if c.key == f"ok_{row_id}"][0].check()
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
    assert len(app.button_group) == 5 * 4                                  # four times of day per medicine
    click(app, "Back")
    assert app.session_state.step == 1 and "Show me the medicines" in texts(app)


def test_every_dose_starts_at_none_and_nothing_reaches_the_plan_until_confirmed(app):
    to_doses(app)
    assert {g.value for g in app.button_group} == {"0"}                      # the app never proposes an amount
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
    assert [t for t in app.text_input if t.key == "other_pack654177_dinner"]
    [t for t in app.text_input if t.key == "other_pack654177_dinner"][0].set_value("media").run()
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
                                  {"breakfast": "0", "lunch": "1", "dinner": "0", "bedtime": "0"}, "", True))
    app.run()
    click(app, "Next: see the plan")
    assert "Pack on several lines" in texts(app) or "several lines" in texts(app)
    assert any("could not be checked" in m.value for m in app.markdown) or any("could not be checked" in c.value for c in app.caption)


def test_the_meta_backend_asks_for_consent_before_the_schedule_photo_leaves(app):
    to_doses(app)
    assert any("LEAVES this computer" in w.value for w in app.warning)
    assert [c.label for c in app.checkbox if c.key == "sheet_consent"] == ["I understand where the picture is sent and want the computer to read it"]


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
