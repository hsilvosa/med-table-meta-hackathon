"""Caregiver app, a four-screen assistant: 1 medicines (photos) -> 2 doses (copy the doctor's schedule) -> 3 check the plan -> 4 print, listen, remind.

  .venv-app/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1

Written for anyone, including people over 80: one task per screen, big text and buttons, plain words, and every screen says what to do next.
Nothing is decided here: the code is read from the box, the medicine comes from AEMPS CIMA, and every dose is picked by the caregiver and
confirmed medicine by medicine. Photos stay on this machine; only code lookups go to the public CIMA API (and, with explicit consent,
one image to the Meta API when a model is used). It also runs inside the 3D room (scripts/start_demo.py), where photos taken with the
virtual phone load by themselves.

This file only lays out the page; the screens are in planner/ (one module per screen) and the logic in src/medtable/.
"""

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from medtable.i18n import LANGUAGES, set_language, tr  # noqa: E402
from planner import common, screen_doses, screen_medicines, screen_plan, table  # noqa: E402
from planner.style import css  # noqa: E402

st.set_page_config(page_title="Medication planner", layout="wide", initial_sidebar_state="collapsed")
st.session_state.setdefault("large_text", False)
st.session_state.setdefault("lang", st.query_params.get("lang", "en") if st.query_params.get("lang") in LANGUAGES else "en")
set_language(st.session_state.lang)
st.markdown(css(1.25 if st.session_state.large_text else 1.0), unsafe_allow_html=True)
common.state_defaults()
t = table.current(date.today())
if common.public_demo():
    common.box("warn", tr("Public online demo"), tr(
        "Try it with the demo photo or the 3D room. Do not upload photos of real prescriptions or of anything showing a name, address or ID "
        "number: pictures are processed on a shared server (photos from the 3D room are deleted after an hour). This is a planning aid, not "
        "medical advice. In this online version the voice, reading the doctor's schedule with Muse Spark and SAM 3 are turned off; they run in "
        'the local installation (<a href="https://github.com/hsilvosa/med-table-meta-hackathon" target="_blank">source code</a>).'))

with st.popover(tr("Settings")):
    st.segmented_control(tr("Language"), list(LANGUAGES), format_func=LANGUAGES.get, key="lang", on_change=lambda: set_language(st.session_state.lang or "en"))
    st.toggle(tr("Larger text"), key="large_text")
    use_smpc = st.toggle(tr("Quote the official leaflets (AEMPS) in the notes"), value=True)
    st.caption(tr("When off, only the checks that need no leaflet text run, and the plan says so."))
    st.button(tr("Start over"), on_click=common.ask_reset, key="start_over", width="stretch")

if st.session_state.get("ask_reset"):
    common.box("warn", tr("Start over?"), tr("This deletes the medicines, the doses and the notes of this plan. It cannot be undone."))
    no, yes = st.columns(2)       # the safe answer first and in colour
    no.button(tr("No, keep my work"), on_click=lambda: st.session_state.pop("ask_reset", None), type="primary", key="reset_no", width="stretch")
    yes.button(tr("Yes, delete everything"), on_click=common.reset_state, key="reset_yes", width="stretch")

if st.session_state.get("scroll_top"):
    st.session_state.scroll_top = False
    st.iframe("<script>const m=window.parent.document.querySelector('[data-testid=\"stMain\"]'); if(m) m.scrollTo(0,0);</script>", height=1)   # fixed text, no user input
common.watch_room()

step = st.session_state.step
if step == 1:
    screen_medicines.render(t)
elif step == 2:
    screen_doses.render(t)
else:
    screen_plan.render(t, step, use_smpc)
