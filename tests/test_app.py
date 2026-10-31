"""The Streamlit app, driven headless with AppTest. No network: CIMA and the SmPC client are replaced."""

import os

import pytest
from fixtures import med
from streamlit.testing.v1 import AppTest

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


def test_demo_photo_gives_recognised_boxes_and_one_that_is_not_in_the_plan(app):
    assert any("does not replace the doctor or the pharmacist" in i.value for i in app.info)
    assert [b.disabled for b in app.button if b.label.startswith("Next:")] == [True]       # nothing to plan yet
    click(app, "Load a demo photo")
    assert not app.exception
    readings = [r for rs in app.session_state.readings.values() for r in rs]
    assert sorted(r.status for r in readings) == ["unverified"] + ["verified"] * 5
    assert len(app.session_state.rows) == 5 and all(r.untouched for r in app.session_state.rows)      # nothing pre-filled
    shown = texts(app)
    assert "Medicines found: 5" in shown and "Box not recognised" in shown and "Not in the plan" in shown
    assert [b.disabled for b in app.button if b.label.startswith("Next:")] == [False]
    assert not any(app.session_state.nocode.values()) and "Box with no code read" not in shown      # a plain grid of codes has no packs without one


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


def test_a_schedule_photo_is_read_only_after_consent_and_fills_the_buttons_without_confirming_anything(env, tmp_path, monkeypatch):
    from medtable import sheet_reader
    (tmp_path / "data" / "world_photos").mkdir(parents=True)
    (tmp_path / "data" / "world_photos" / "latest.jpg").write_bytes(b"x")
    rows = [{"medicine": "Enalapril 10 mg comprimidos", "breakfast": "1", "lunch": "0", "dinner": "1/2", "bedtime": "0", "remarks": "con comida", "confirmed": False},
            {"medicine": "Atorvastatina 20 mg", "breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "1", "remarks": "", "confirmed": False}]
    monkeypatch.setattr(sheet_reader, "read_sheet", lambda path, backend=None, consent=False: sheet_reader.SheetReading(rows, [], "meta", 0.0) if consent is True else 1 / 0)    # the tick reaches the reader
    named = {**MEDS, "654177": med("654177", "ENALAPRIL TESTLAB 10 mg COMPRIMIDOS", ["ENALAPRIL"], "C09AA02")}      # a name the sheet line can match unambiguously
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: named.get("".join(c for c in cn if c.isdigit())[:6]))
    at = AppTest.from_file(APP, default_timeout=120).run()
    to_doses(at)
    assert any("LEAVES this computer" in w.value for w in at.warning)         # it says where the picture goes, and waits for the tick
    assert [b.disabled for b in at.button if b.label.startswith("Read the latest room photo")] == [True]
    [c for c in at.checkbox if c.key == "sheet_consent"][0].check()
    at.run()
    click(at, "Read the latest room photo")
    assert not at.exception
    assert [g.value for g in doses_of(at) if g.key.startswith("dose_pack654177_")] == ["1", "0", "1/2", "0"]     # the buttons SHOW what was read
    assert at.session_state.rows[0].remarks == "con comida" and not any(r.confirmed for r in at.session_state.rows)
    assert [g.value for g in doses_of(at) if g.key.startswith("dose_sheet")] == ["0", "0", "0", "1"]           # a line with no box becomes its own row


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


def test_changing_an_amount_after_ticking_needs_a_new_tick(app):
    to_doses(app)
    confirm(app, "pack654177")                                              # ticked first, amounts after: the tick no longer stands
    pick(app, "pack654177", "breakfast", "1")
    assert not next(r for r in app.session_state.rows if r.cn == "654177").confirmed
    confirm(app, "pack654177")
    assert "1 of 5 medicines ready for the plan" in [p.text for p in app.get("progress")][0]


def test_codes_read_without_a_connection_are_not_verified_and_can_be_tried_again(env, monkeypatch):
    from medtable import cima
    from medtable.resolve import Resolver
    real = Resolver.by_cn
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: (_ for _ in ()).throw(cima.Unreachable("down")))
    at = AppTest.from_file(APP, default_timeout=120).run()
    click(at, "Load a demo photo")
    assert "No connection to the official database" in texts(at) and "Medicines found: 0" in texts(at)
    monkeypatch.setattr(Resolver, "by_cn", real)                             # the connection is back
    click(at, "Try again")
    assert "Medicines found: 5" in texts(at) and not at.exception


def test_the_whole_flow_can_be_done_in_spanish(env):
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["lang"] = "es"
    at.run()
    assert "Cada caja se identifica por el código impreso en ella" in texts(at) and any("no sustituye al médico" in i.value for i in at.info)
    click(at, "Cargar una foto de prueba")
    assert "Medicamentos encontrados: 5" in texts(at) and "Caja no reconocida" in texts(at)
    click(at, "Siguiente: elegir las dosis")
    pick(at, "pack654177", "breakfast", "1")
    confirm(at, "pack654177")
    click(at, "Siguiente: ver el plan")
    agenda = [m.value for m in at.markdown if "mt-agenda" in m.value][-1]
    assert "Desayuno" in agenda and "1 comprimido" in agenda and not at.exception


def test_the_public_demo_warns_and_offers_no_model_upload_and_shows_only_this_visitors_room_photo(env, tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    (tmp_path / "data" / "world_photos" / "someone-else-1").mkdir(parents=True)
    (tmp_path / "data" / "world_photos" / "someone-else-1" / "latest.jpg").write_bytes(b"x")       # another visitor's photo
    (tmp_path / "data" / "world_photos" / "latest.jpg").write_bytes(b"x")                           # the local installation's shared photo
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["session"] = "visitor-0001"
    at.run()
    assert "Public online demo" in texts(at) and "Do not upload photos of real prescriptions" in texts(at)
    assert not [b for b in at.button if b.label.startswith("Load the latest room photo")]           # not this visitor's photo
    assert not [e for e in at.expander if "no code I can read" in e.label]                         # SAM 3 and the model call are off
    to_doses(at)
    assert not [e for e in at.expander if "doctor's schedule" in e.label] and not at.exception
