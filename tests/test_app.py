"""The Streamlit app, driven headless with AppTest. No network: CIMA and the SmPC client are replaced."""

import os

import pandas as pd
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


def test_starts_without_errors_and_shows_the_disclaimer(app):
    assert not app.exception
    assert any("does not replace the doctor or the pharmacist" in i.value for i in app.info)


def test_demo_photo_gives_verified_packs_and_one_unverified_that_is_not_planned(app):
    click(app, "Load a demo photo")
    assert not app.exception
    readings = [r for rs in app.session_state.readings.values() for r in rs]
    assert sorted(r.status for r in readings) == ["unverified"] + ["verified"] * 5
    assert len(app.session_state.sheet) == 5  # one empty row per verified pack, nothing pre-filled
    assert set(app.session_state.sheet["confirmed"]) == {False}
    assert not any(app.session_state.sheet[s].ne("0").any() for s in ("breakfast", "lunch", "dinner", "bedtime"))  # the app never proposes a dose
    assert any("Code that could not be verified" in m.value and "Left out of the plan" in m.value for m in app.markdown)


def test_nothing_reaches_the_plan_until_the_caregiver_confirms(app):
    click(app, "Load a demo photo")
    assert any("Nothing in the plan yet" in i.value for i in app.info)
    sheet = app.session_state.sheet.copy()
    sheet.loc[0, ["breakfast", "confirmed"]] = ["1", True]
    app.session_state.sheet = sheet
    app.run()
    agenda = [m.value for m in app.markdown if "mt-agenda" in m.value][-1]
    breakfast, lunch = agenda.split("Lunch")[0], agenda.split("Lunch")[1]
    assert "MEDICAMENTO 654177" in breakfast and "1 tablet" in breakfast
    assert "MEDICAMENTO 654177" not in lunch


def test_a_pack_on_two_lines_is_blocked_in_the_ui(app):
    click(app, "Load a demo photo")
    sheet = app.session_state.sheet.copy()
    sheet.loc[0, ["breakfast", "confirmed"]] = ["1", True]
    sheet.loc[len(sheet)] = [sheet.loc[0, "medicine"], "0", "1", "0", "0", "", True, sheet.loc[0, "cn"]]
    app.session_state.sheet = sheet
    app.run()
    assert any("Pack on several lines" in m.value for m in app.markdown)
    assert any("could not be checked" in m.value for m in app.markdown) or any("could not be checked" in c.value for c in app.caption)


def test_meta_backend_warns_and_the_sheet_reader_needs_consent(app):
    assert any("LEAVES this computer" in w.value for w in app.warning)
    assert [b.disabled for b in app.button if b.label == "Read the sheet"] == [True]


def test_reset_clears_everything(app):
    click(app, "Load a demo photo")
    click(app, "Start over")
    assert len(app.session_state.sheet) == 0 and not app.session_state.readings and not app.exception


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
