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
    assert any("no sustituye al médico ni al farmacéutico" in i.value for i in app.info)


def test_demo_photo_gives_verified_packs_and_one_unverified_that_is_not_planned(app):
    click(app, "Cargar foto de ejemplo")
    assert not app.exception
    readings = [r for rs in app.session_state.readings.values() for r in rs]
    assert sorted(r.status for r in readings) == ["unverified"] + ["verified"] * 5
    assert len(app.session_state.sheet) == 5  # one empty row per verified pack, nothing pre-filled
    assert set(app.session_state.sheet["confirmado"]) == {False}
    assert not any(app.session_state.sheet[s].ne("0").any() for s in ("desayuno", "comida", "cena", "acostarse"))  # the app never proposes a dose
    assert any("no se pudo verificar" in e.value for e in app.error)


def test_nothing_reaches_the_plan_until_the_caregiver_confirms(app):
    click(app, "Cargar foto de ejemplo")
    assert any("El plan está vacío" in c.value for c in app.caption)
    sheet = app.session_state.sheet.copy()
    sheet.loc[0, ["desayuno", "confirmado"]] = ["1", True]
    app.session_state.sheet = sheet
    app.run()
    table = [d.value for d in app.dataframe if "Desayuno" in d.value.columns][-1]
    assert "MEDICAMENTO 654177" in table["Desayuno"][0] and "1 comprimido" in table["Desayuno"][0]
    assert table["Comida"][0] == "-"


def test_a_pack_on_two_lines_is_blocked_in_the_ui(app):
    click(app, "Cargar foto de ejemplo")
    sheet = app.session_state.sheet.copy()
    sheet.loc[0, ["desayuno", "confirmado"]] = ["1", True]
    sheet.loc[len(sheet)] = [sheet.loc[0, "medicamento"], "0", "1", "0", "0", "", True, sheet.loc[0, "cn"]]
    app.session_state.sheet = sheet
    app.run()
    assert any("varias líneas" in e.value for e in app.error)
    assert any("no se han consultado" in c.value.lower() or "no se pudo consultar" in c.value.lower() for c in app.caption) or any("no se ha hecho" in w.value for w in app.warning)


def test_meta_backend_warns_and_the_sheet_reader_needs_consent(app):
    assert any("SALE de este equipo" in w.value for w in app.warning)
    assert [b.disabled for b in app.button if b.label == "Leer la hoja"] == [True]


def test_reset_clears_everything(app):
    click(app, "Cargar foto de ejemplo")
    click(app, "Empezar de nuevo")
    assert len(app.session_state.sheet) == 0 and not app.session_state.readings and not app.exception
