"""Caregiver app, a four-screen assistant: 1 medicines (photos) -> 2 doses (copy the doctor's schedule) -> 3 check the plan -> 4 print, listen, remind.

  .venv-app/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1

Written for anyone, including people over 80: one task per screen, big text and buttons, plain words, and every screen says what to do next.
Nothing is decided here: the code is read from the box, the medicine comes from AEMPS CIMA, and every dose is picked by the caregiver and
confirmed medicine by medicine. Photos stay on this machine; only code lookups go to the public CIMA API (and, with explicit consent,
one image to the Meta API when a model is used). It also runs inside the 3D room (scripts/start_demo.py), where photos taken with the
virtual phone load by themselves.
"""

import base64
import html
import re
import shutil
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from medtable import candidates, decode, identify, sheet_reader, synthetic, vlm, voice  # noqa: E402
from medtable.calendar_pdf import render_pdf  # noqa: E402
from medtable.findings import NOT_A_FULL_CHECK, explain_problem  # noqa: E402
from medtable.form import CHOICE_LABELS, CHOICE_VALUES, OTHER, Row, choice_for, merge_read_rows, sync_pack_rows  # noqa: E402
from medtable.pipeline import make_plan, manual_pack  # noqa: E402
from medtable.plan import DEFAULT_TIMES, NOT_CONFIRMED, SLOT_LABELS, to_ics  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402
from medtable.rules import Pack  # noqa: E402
from medtable.schedule import SLOTS  # noqa: E402
from medtable.smpc import Smpc  # noqa: E402

DEMO_ITEMS = [("654177", "281231"), ("662025", "270430"), ("715240", "250600"), ("677379", "280131"), ("656012", "271130"), ("100008", "281231")]
LATEST_PHOTO = Path("data/world_photos/latest.jpg")
LOCAL_PHOTOS = Path("data/cima/images/full")
STEPS = ["Medicines", "Doses", "Check", "Print and listen"]
SLOT_HINT = {"breakfast": "morning", "lunch": "midday", "dinner": "evening", "bedtime": "before sleep"}

st.set_page_config(page_title="Medication planner", layout="wide", initial_sidebar_state="collapsed")
EMBEDDED = st.query_params.get("room") == "1"   # inside the 3D room's side panel: narrower layout


def css(scale: float) -> str:
    return f"""
<style>
html {{ font-size: {int(18 * scale)}px; }}
.block-container {{ padding-top: {1 if EMBEDDED else 3.5}rem; max-width: 820px; }}
h1, h2, h3 {{ letter-spacing: 0; }}
.stButton > button, .stDownloadButton > button {{ min-height: 3.1rem; font-size: 1.05rem; font-weight: 650; border-radius: 12px; }}
.stButton button p, .stDownloadButton button p {{ font-size: 1.15rem !important; font-weight: 700 !important; }}
[data-testid="stButtonGroup"] button p {{ font-size: 1.15rem !important; font-weight: 700 !important; }}
[data-testid="stBaseButton-primary"] {{ background: #1b5e8a; border-color: #1b5e8a; }}
[data-testid="stBaseButton-primary"]:disabled {{ background: #c9d3dd; border-color: #c9d3dd; color: #fff; }}
[data-testid="stButtonGroup"] button {{ min-height: 2.9rem; font-size: 1.1rem; font-weight: 650; }}
[data-testid="stWidgetLabel"] p {{ font-size: 1.05rem; font-weight: 650; color: #1f2933; }}
[data-testid="stCheckbox"] label p {{ font-size: 1.1rem; font-weight: 600; }}
[data-testid="stCheckbox"] label > div:nth-of-type(1) {{ width: 1.9rem; height: 1.9rem; min-width: 1.9rem; border-width: 3px; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: #1b5e8a !important; border-color: #1b5e8a !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: #fff !important; }}
[data-testid="stTabs"] button p {{ font-size: 1.05rem; font-weight: 650; }}
.mt-title {{ font-size: 1.75rem !important; font-weight: 800 !important; margin: .2rem 0 .1rem !important; line-height: 1.2 !important; color: #14202b; }}
.mt-lead {{ font-size: 1.12rem !important; color: #33404d; margin: 0 0 .8rem !important; line-height: 1.5 !important; }}
.mt-steps {{ display: flex; gap: 6px; margin: .2rem 0 1rem; }}
.mt-s {{ flex: 1; text-align: center; font-size: .82rem; color: #5d6875; border-top: 6px solid #d3dae3; padding-top: 6px; line-height: 1.2; }}
.mt-s b {{ display: block; font-size: .95rem; color: #5d6875; }}
.mt-s.done {{ border-color: #1f8a5b; }} .mt-s.done b {{ color: #1f8a5b; }}
.mt-s.cur {{ border-color: #1b5e8a; color: #1b5e8a; font-weight: 700; }} .mt-s.cur b {{ color: #1b5e8a; }}
.mt-box {{ border-radius: 12px; padding: 12px 16px; margin: 10px 0; line-height: 1.45; font-size: 1.02rem; }}
.mt-box.tip {{ background: #eef5fb; border: 1px solid #c4dcf0; }}
.mt-box.warn {{ background: #fff6e0; border: 1px solid #f0c777; }}
.mt-box.bad {{ background: #fdeeee; border: 1px solid #eba5a5; }}
.mt-box.ok {{ background: #eaf7f0; border: 1px solid #8fd0ad; }}
.mt-box b.t {{ display: block; font-size: 1.08rem; margin-bottom: 2px; }}
.mt-chip {{ display: inline-block; padding: 2px 11px; border-radius: 999px; font-size: .85rem; font-weight: 700; margin: 0 5px 5px 0; }}
.mt-chip.ok {{ background: #d6f0e2; color: #0f5a35; }} .mt-chip.warn {{ background: #ffecc2; color: #6f4800; }}
.mt-chip.bad {{ background: #fbd7d7; color: #8f1818; }} .mt-chip.grey {{ background: #e4e9ef; color: #323d49; }}
.mt-card {{ display: flex; gap: 14px; align-items: center; border: 1px solid #d7dde4; border-radius: 14px; padding: 12px 14px; margin: 0 0 10px; background: #fff; }}
.mt-card.plain {{ border: none; padding: 0; margin: 0 0 6px; }}
.mt-pic {{ flex: none; width: 112px; height: 84px; object-fit: contain; background: #f4f6f8; border-radius: 8px; }}
.mt-name {{ font-weight: 750; line-height: 1.25; font-size: 1.1rem; margin: 2px 0 6px; }}
.mt-meta {{ color: #55606e; font-size: .88rem; }}
.mt-agenda {{ width: 100%; border-collapse: collapse; }}
.mt-agenda td {{ padding: 14px 12px; border-bottom: 2px solid #e3e7ec; vertical-align: top; font-size: 1.12rem; }}
.mt-agenda tr:last-child td {{ border-bottom: none; }}
.mt-slot {{ width: 8.5rem; font-weight: 800; }} .mt-time {{ display: block; color: #55606e; font-weight: 500; font-size: .9rem; }}
.mt-dose {{ font-weight: 800; }} .mt-empty {{ color: #7d8793; }}
.mt-quote {{ color: #323d49; font-style: italic; margin-top: 6px; }}
.mt-hint {{ color: #55606e; font-size: .95rem !important; margin: -4px 0 6px !important; }}
</style>"""


if "large_text" not in st.session_state:
    st.session_state.large_text = False
st.markdown(css(1.25 if st.session_state.large_text else 1.0), unsafe_allow_html=True)
esc = html.escape


@st.cache_resource
def resolver() -> Resolver:
    return Resolver()


class CachedSmpc:
    """CIMA sections are cached on disk; this also remembers 'no such section' answers for the session."""

    def __init__(self) -> None:
        self.inner, self.missing = Smpc(), set()

    def section(self, nregistro: str, section: str):
        if (nregistro, section) in self.missing:
            return None
        result = self.inner.section(nregistro, section)
        if result is None:
            self.missing.add((nregistro, section))
        return result


@st.cache_resource
def smpc_source() -> CachedSmpc:
    return CachedSmpc()


def reset_state() -> None:
    shutil.rmtree("data/cache/segments", ignore_errors=True)  # crops of the photos that SAM wrote to disk
    for key in list(st.session_state.keys()):
        if key not in ("large_text",):
            st.session_state.pop(key, None)


def state_defaults() -> None:
    st.session_state.setdefault("step", 1)
    st.session_state.setdefault("readings", {})  # photo name -> list[Reading]
    st.session_state.setdefault("photos", {})
    st.session_state.setdefault("manual", [])
    st.session_state.setdefault("rows", [])  # list[Row]
    st.session_state.setdefault("room_seen", time.time())  # only room photos taken after the session started load by themselves


def go(step: int) -> None:
    st.session_state.step = step
    st.session_state.scroll_top = True


def add_photo(name: str, image: np.ndarray) -> None:
    with st.spinner(f"Reading the codes in {name}..."):
        st.session_state.readings[name] = identify.identify(image, resolver())
    st.session_state.photos[name] = image


def official_photo(medicine) -> str | None:
    for kind in ("materialas", "formafarmac"):
        local = LOCAL_PHOTOS / kind / f"{medicine.nregistro}.jpg"
        if local.exists():
            return str(local)
        if medicine.photos.get(kind):
            return medicine.photos[kind]
    return None


def data_uri(image: np.ndarray, width: int = 220) -> str:
    scale = width / image.shape[1]
    small = cv2.resize(image, (width, max(1, int(image.shape[0] * scale))), interpolation=cv2.INTER_AREA) if scale < 1 else image
    ok, buffer = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode()


def picture(source: str | np.ndarray | None) -> str:
    """An <img> for a card: a downsized data URI for local files and arrays, the URL itself for remote photos."""
    if source is None:
        return '<div class="mt-pic"></div>'
    if isinstance(source, str) and source.startswith("http"):
        return f'<img class="mt-pic" src="{esc(source)}">'
    image = cv2.imread(source) if isinstance(source, str) else source
    return f'<img class="mt-pic" src="{data_uri(image)}">' if image is not None else '<div class="mt-pic"></div>'


def card(source, body: str, plain: bool = False) -> None:
    st.markdown(f'<div class="mt-card{" plain" if plain else ""}">{picture(source)}<div>{body}</div></div>', unsafe_allow_html=True)


def box(kind: str, title: str, text: str = "") -> None:
    st.markdown(f'<div class="mt-box {kind}"><b class="t">{esc(title)}</b>{text}</div>', unsafe_allow_html=True)


def source_html(source: str) -> str:
    """A citation as small text, with the long URL turned into a link."""
    match = re.match(r"(.*?):?\s*(https?://\S+)$", source)
    return f'{esc(match.group(1))}. <a href="{esc(match.group(2))}" target="_blank">Open the official page</a>' if match else esc(source)


def chip(text: str, kind: str = "grey") -> str:
    return f'<span class="mt-chip {kind}">{esc(text)}</span>'


def expiry_chip(expiry: date | None, today: date) -> str:
    if expiry is None:
        return chip("Expiry date unknown", "warn")
    if expiry < today:
        return chip(f"Expired on {expiry.isoformat()}", "bad")
    if expiry <= today + timedelta(days=30):
        return chip(f"Expires on {expiry.isoformat()}", "warn")
    return chip(f"Expires on {expiry.isoformat()}", "grey")


def header(step: int, title: str, lead: str) -> None:
    cells = "".join(f'<div class="mt-s {"cur" if i == step else "done" if i < step else ""}"><b>{i}</b>{esc(name)}</div>' for i, name in enumerate(STEPS, 1))
    st.markdown(f'<div class="mt-steps">{cells}</div><p class="mt-title">{esc(title)}</p><p class="mt-lead">{lead}</p>', unsafe_allow_html=True)


def nav(back: int | None, forward: int | None, forward_label: str = "", enabled: bool = True, why_not: str = "") -> None:
    left, right = st.columns(2) if forward else (st.container(), None)
    if back:
        left.button("Back", on_click=go, args=(back,), key=f"back{back}_{st.session_state.step}", width="stretch")
    if forward:
        right.button(forward_label, on_click=go, args=(forward,), type="primary", disabled=not enabled, key=f"next{forward}", width="stretch")
        if not enabled and why_not:
            right.markdown(f'<p class="mt-hint">{esc(why_not)}</p>', unsafe_allow_html=True)


@st.fragment(run_every="2s")
def watch_room() -> None:
    """Photos taken with the virtual phone in the 3D room load here by themselves."""
    if not LATEST_PHOTO.exists() or LATEST_PHOTO.stat().st_mtime <= st.session_state.room_seen:
        return
    st.session_state.room_seen = LATEST_PHOTO.stat().st_mtime
    image = cv2.imread(str(LATEST_PHOTO))
    if image is not None:
        add_photo(f"room_{time.strftime('%H:%M:%S', time.localtime(LATEST_PHOTO.stat().st_mtime))}", image)
        st.session_state.step = 1
        st.rerun()


state_defaults()
today = date.today()

# ---- the readings, the sheet rows and the plan are computed on every screen (cheap, cached lookups) -----------------------
seen_raw: set[str] = set()
entries = []          # (photo name, reading), one per physical pack (same code text = same pack)
for name, rs in st.session_state.readings.items():
    for r in rs:
        if r.raw not in seen_raw:
            seen_raw.add(r.raw)
            entries.append((name, r))
readings = [r for _, r in entries]
verified = [r for r in readings if r.status == "verified" and r.medicine]
unverified = [(n, r) for n, r in entries if r.status != "verified" or not r.medicine]
medicines = [r.medicine for r in verified] + [p.medicine for p in st.session_state.manual]
sync_pack_rows(st.session_state.rows, medicines)
rows: list[Row] = st.session_state.rows

# ---- settings (small, out of the way) ---------------------------------------------------------------------------------------
with st.popover("Settings"):
    st.toggle("Larger text", key="large_text")
    use_smpc = st.toggle("Quote the official leaflets (AEMPS) in the notes", value=True)
    st.caption("When off, only the checks that need no leaflet text run, and the plan says so.")
    st.button("Start over", on_click=reset_state, key="start_over", width="stretch")

if st.session_state.get("scroll_top"):
    st.session_state.scroll_top = False
    st.iframe("<script>const m=window.parent.document.querySelector('[data-testid=\"stMain\"]'); if(m) m.scrollTo(0,0);</script>", height=1)   # fixed text, no user input
watch_room()
step = st.session_state.step

# =============================================================================================================================
# Screen 1: the medicines
# =============================================================================================================================
if step == 1:
    header(1, "Show me the medicines",
           "Take one photo of the medicine boxes on the table. I read the code printed on each box and look it up in the official Spanish medicine database.")
    st.info("This is a helper for planning. It gives no medical advice and does not replace the doctor or the pharmacist.")
    box("tip", "For a good photo", "Put the boxes on a table with the printed code facing up. Hold the phone about 50 cm (20 inches) above them, "
        "so the little square code on each box is sharp.")
    tab_room, tab_upload, tab_code = st.tabs(["Photo from the 3D room", "Upload a photo", "Type a code"]) if EMBEDDED else \
        st.tabs(["Upload a photo", "Type a code", "Demo photos"])
    if not EMBEDDED:
        tab_upload, tab_code, tab_room = tab_room, tab_upload, tab_code
    with tab_room:
        if EMBEDDED:
            st.write("Use the buttons at the bottom of the room: walk to a table, hold the phone over it and take the photo. "
                     "It appears here by itself in a few seconds.")
        else:
            st.write("Photos made for trying the tool. They contain no real medication or patient.")
        c1, c2 = st.columns(2)
        if LATEST_PHOTO.exists() and c1.button("Load the latest room photo", width="stretch"):
            image = cv2.imread(str(LATEST_PHOTO))
            if image is None:
                st.error("The latest room photo could not be opened.")
            else:
                add_photo(f"room_{time.strftime('%H:%M:%S', time.localtime(LATEST_PHOTO.stat().st_mtime))}", image)
                st.rerun()
        if c2.button("Load a demo photo", width="stretch"):
            add_photo("demo", synthetic.demo_photo(DEMO_ITEMS))
            st.rerun()
    with tab_upload:
        uploads = st.file_uploader("Choose a photo of the boxes (JPG or PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
        current = {u.name for u in uploads or []}
        for gone in [n for n in st.session_state.readings if n not in current and n != "demo" and not n.startswith("room_")]:  # a removed upload must not stay in the plan
            st.session_state.readings.pop(gone, None)
            st.session_state.photos.pop(gone, None)
        fresh = False
        for upload in uploads or []:
            if upload.name not in st.session_state.readings:
                decoded = cv2.imdecode(np.frombuffer(upload.getvalue(), np.uint8), cv2.IMREAD_COLOR)
                if decoded is None:
                    st.error(f"{upload.name} could not be opened as a picture. Use a JPG or PNG file (iPhone HEIC photos must be converted first).")
                else:
                    add_photo(upload.name, decoded)
                    fresh = True
        if fresh:
            st.rerun()
    with tab_code:
        st.write("Every box has a national code (C.N.) printed on it: six or seven digits, for example 848226.9. Type it here to add the medicine without a photo.")
        typed = st.text_input("The code on the box", placeholder="848226.9")
        if st.button("Add this medicine", width="stretch") and typed:
            pack, problem = manual_pack(typed, resolver())
            if problem:
                st.error(problem)
            elif pack.medicine.cn not in {p.medicine.cn for p in st.session_state.manual}:
                st.session_state.manual.append(pack)
                st.rerun()

    st.markdown(f'<p class="mt-title" style="font-size:1.35rem;margin-top:1.2rem">Medicines found: {len(medicines)}</p>', unsafe_allow_html=True)
    if not entries and not st.session_state.manual:
        box("tip", "Nothing yet", "Add a photo or type a code above. The medicines I recognise will appear here.")
    for reading in verified:
        card(official_photo(reading.medicine), f'<div class="mt-name">{esc(reading.medicine.name)}</div>' + chip("Recognised from its code", "ok")
             + expiry_chip(reading.expiry, today) + f'<div class="mt-meta">National code {esc(reading.medicine.cn)}</div>')
    for pack in st.session_state.manual:
        card(official_photo(pack.medicine), f'<div class="mt-name">{esc(pack.medicine.name)}</div>' + chip("Added by code", "ok")
             + f'<div class="mt-meta">National code {esc(pack.medicine.cn)}</div>')
    if unverified:
        box("bad", f"{len(unverified)} box(es) could not be recognised",
            "These are <b>not</b> in the plan. A box is only accepted when its code can be read and matches the official database. "
            "You can type the national code printed on the box (tab \"Type a code\"), or try a closer, sharper photo.")
    for name, r in unverified:
        image, crop = st.session_state.photos.get(name), None
        if image is not None and r.bbox:
            x0, y0, x1, y1 = r.bbox
            pad = max(x1 - x0, y1 - y0)
            crop = image[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad]
            crop = crop if crop.size else None
        card(crop, f'<div class="mt-name">A code I could not accept</div>{chip("Not in the plan", "bad")}'
             f'<div class="mt-meta">{esc("; ".join(explain_problem(p) for p in r.problems) or "reason unknown")}</div>')

    with st.expander("A box has no code I can read? Find it in the photo and choose it from the database"):
        st.write("The computer looks for boxes in the photo that have no readable code and suggests possible medicines from the official database. "
                 "**Nothing enters the plan until you choose one and confirm it against the official picture.**")
        photos = st.session_state.photos
        if st.button("Look for boxes without a code", disabled=not photos, width="stretch"):
            found = []
            for name, image in photos.items():
                folder = Path("data/cache/segments") / Path(name.replace(":", "")).stem
                folder.mkdir(parents=True, exist_ok=True)
                photo_path = folder / "photo.png"
                cv2.imwrite(str(photo_path), image)
                try:
                    with st.spinner(f"Looking for boxes in {name} (about 30 seconds)..."):
                        boxes = candidates.segment(photo_path, folder)
                except Exception as exc:  # no GPU, SAM environment missing: typing the national code still works
                    st.error(f"This step could not run ({exc}). You can type the code on the box instead.")
                    continue
                codes = [decode.Detection(r.raw, r.bbox, r.method) for r in st.session_state.readings.get(name, [])]
                found += [(name, b) for b in candidates.boxes_without_code(boxes, codes)]
            st.session_state.unmatched = found
        for number, (name, found_box) in enumerate(st.session_state.get("unmatched", [])[:12]):
            st.image(str(found_box.crop), caption=f"Box {number + 1}", width=170)
            key = f"proposal_{name}_{found_box.crop.name}"
            backend = vlm.backend_name()
            ok = st.checkbox("I understand this small picture is sent to the Meta API (only do this if it shows no personal data)", key=f"consent_{key}") if backend == "meta" else True
            if st.button("Suggest medicines", key=f"btn_{key}", disabled=not ok):
                try:
                    with st.spinner("Asking the model and the official database..."):
                        st.session_state[key] = candidates.propose(found_box.crop, resolver())
                except Exception as exc:  # noqa: BLE001
                    st.error(f"The model could not be reached ({exc}).")
            proposal = st.session_state.get(key)
            if proposal:
                if proposal.note:
                    st.info(proposal.note)
                labels = {f"{c.medicine.name} ({', '.join(c.why) or 'no clear match'})": c for c in proposal.candidates}
                choice = st.radio("Which medicine is this?", ["None of these / I do not know", *labels], key=f"radio_{key}") if labels else None
                shown = list(labels.values())[:3]
                for col, cand in zip(st.columns(max(len(shown), 1)), shown):
                    url = official_photo(cand.medicine)
                    if url:
                        col.image(url, caption=f"{cand.medicine.name[:30]} (official picture)", width=120)
                if choice in labels and st.button("Yes, this is the medicine", key=f"ok_{key}", type="primary"):
                    picked = labels[choice].medicine
                    if picked.cn not in {p.medicine.cn for p in st.session_state.manual}:
                        st.session_state.manual.append(Pack(picked, "confirmed"))
                        st.rerun()
    st.write("")
    nav(None, 2, "Next: choose the doses", enabled=bool(medicines), why_not="Add at least one medicine to continue.")

# =============================================================================================================================
# Screen 2: the doses
# =============================================================================================================================
elif step == 2:
    header(2, "Choose the doses",
           "Copy the doctor's schedule. For each medicine, choose <b>how many to take</b> at each time of day. When you have checked a medicine against "
           "the doctor's paper, tick <b>Yes, this matches the doctor's schedule</b>. I never choose an amount for you, and medicines that are not ticked stay out of the plan.")
    with st.expander("Have a photo of the doctor's schedule? Let the computer copy it (optional)"):
        backend = vlm.backend_name()
        if backend == "meta":
            st.warning("The photo LEAVES this computer and goes to the Meta API. Use it only for a sheet without personal data "
                       "(no name, ID number or address), or set VLM_BACKEND=local to keep it on this machine.")
        else:
            st.caption("Local model: the picture does not leave this computer.")
        sheet_photo = st.file_uploader("Photo of the schedule", type=["jpg", "jpeg", "png"], key="sheet_photo")
        consent = st.checkbox("I understand where the picture is sent and want the computer to read it", key="sheet_consent") if backend == "meta" else True
        if st.button("Read the schedule", disabled=not (sheet_photo and consent), width="stretch"):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / sheet_photo.name
                path.write_bytes(sheet_photo.getvalue())
                try:
                    with st.spinner("Reading the schedule..."):
                        read = sheet_reader.read_sheet(path)
                except Exception as exc:  # network, budget cap, server not running: tell the caregiver, keep manual entry available
                    st.error(f"The schedule could not be read ({exc}). You can choose the doses by hand below.")
                else:
                    packs_now = [Pack(m, "verified") for m in medicines]
                    changed, merge_notes = merge_read_rows(rows, read.rows, packs_now)
                    for row in changed:   # forget the on-screen state of those rows so the buttons show what was read
                        for slot in SLOTS:
                            st.session_state.pop(f"dose_{row.id}_{slot}", None)
                            st.session_state.pop(f"other_{row.id}_{slot}", None)
                        st.session_state.pop(f"remarks_{row.id}", None)
                    st.session_state.sheet_notes = read.problems + merge_notes + ["Check every medicine against the paper: a computer reading can contain mistakes."]
        for note in st.session_state.get("sheet_notes", []):
            st.warning(note)

    def set_dose(row: Row, slot: str) -> None:
        picked = st.session_state[f"dose_{row.id}_{slot}"]
        if picked is None:      # clicking the selected button again would clear it: keep the choice
            st.session_state[f"dose_{row.id}_{slot}"] = choice_for(row.doses[slot])
        elif picked != OTHER:
            row.doses[slot] = picked
        elif choice_for(row.doses[slot]) != OTHER:
            row.doses[slot] = ""        # "Other" with nothing typed yet: the plan reports it instead of guessing

    def set_other(row: Row, slot: str) -> None:
        row.doses[slot] = st.session_state[f"other_{row.id}_{slot}"].strip()

    def set_field(row: Row, field: str, key: str) -> None:
        setattr(row, field, st.session_state[key].strip() if field == "remarks" else st.session_state[key])

    for row in rows:
        pack = next((m for m in medicines if m.cn == row.cn), None)
        with st.container(border=True):
            body = f'<div class="mt-name">{esc(row.medicine)}</div>'
            if pack:
                body += chip("Box on the table", "ok")
            else:
                body += chip("No matching box in the photos", "warn")
            if row.sheet_name and row.sheet_name != row.medicine:
                body += f'<div class="mt-meta">The schedule says: {esc(row.sheet_name)}</div>'
            card(official_photo(pack) if pack else None, body, plain=True)
            for slot in SLOTS:
                st.segmented_control(f"{SLOT_LABELS[slot]} ({SLOT_HINT[slot]}): how many?", CHOICE_VALUES + [OTHER], format_func=CHOICE_LABELS.get,
                                     default=choice_for(row.doses[slot]), key=f"dose_{row.id}_{slot}", on_change=set_dose, args=(row, slot))
                if choice_for(row.doses[slot]) == OTHER:
                    st.text_input("Type the amount (for example 4 or 2,5)", value=row.doses[slot], key=f"other_{row.id}_{slot}", on_change=set_other, args=(row, slot))
            st.text_input("Note (optional), for example: with food", value=row.remarks, key=f"remarks_{row.id}", on_change=set_field, args=(row, "remarks", f"remarks_{row.id}"))
            st.checkbox("Yes, this matches the doctor's schedule", value=row.confirmed, key=f"ok_{row.id}", on_change=set_field, args=(row, "confirmed", f"ok_{row.id}"))
            if row.confirmed and row.has_dose:
                st.markdown(chip("Will be in the plan", "ok"), unsafe_allow_html=True)
            elif row.confirmed:
                st.markdown(chip("Ticked, but every amount is None", "warn"), unsafe_allow_html=True)
            else:
                st.markdown(chip("Not in the plan yet: choose the amounts, then tick the box", "grey"), unsafe_allow_html=True)

    with st.expander("A medicine on the schedule that has no box on the table"):
        st.write("Type its name as written on the schedule. The plan will list it as \"on the schedule but not on the table\".")
        extra = st.text_input("Name on the schedule", key="extra_name")
        if st.button("Add this line", disabled=not extra.strip(), width="stretch"):
            rows.append(Row(f"hand{len(rows) + 1}", extra.strip()))
            st.session_state.extra_name = ""
            st.rerun()
    st.write("")
    ready = sum(1 for r in rows if r.confirmed and r.has_dose)
    nav(1, 3, "Next: see the plan", enabled=bool(rows), why_not="There are no medicines yet. Go back and add one.")
    st.caption(f"{ready} of {len(rows)} medicine(s) will be in the plan.")

# =============================================================================================================================
# Screens 3 and 4 need the plan
# =============================================================================================================================
else:
    records = [r.as_record() for r in rows]
    with st.spinner("Preparing the plan..."):
        result = make_plan(readings, st.session_state.manual, records, smpc_source() if use_smpc else None, today)
    plan = result.plan
    review = [f for f in plan.findings if f.kind != "unverified_item" and f.severity == "review"]
    info = [f for f in plan.findings if f.kind != "unverified_item" and f.severity == "info"]
    pending = [what for what, why in plan.not_included if why == NOT_CONFIRMED]      # waiting for the caregiver, not a problem yet
    left_out = [(what, why) for what, why in plan.not_included if why != NOT_CONFIRMED]
    doses = len(plan.entries)

    if step == 3:
        header(3, "Check the plan", "This is exactly what will be printed. Read it through, and read what was left out and why.")
        if not doses:
            box("warn", "Nothing in the plan yet",
                "Go back to <b>Doses</b>, choose the amounts and tick <b>Yes, this matches the doctor's schedule</b> for at least one medicine."
                + (f" Waiting for you: {len(pending)} medicine(s)." if pending else ""))
        rows_html = []
        for slot in SLOTS:
            time_text = st.session_state.get(f"t_{slot}", DEFAULT_TIMES[slot])
            time_text = time_text.strftime("%H:%M") if hasattr(time_text, "strftime") else time_text
            items = "".join(f'<div style="margin-bottom:6px"><span class="mt-dose">{esc(e.written())}</span> of {esc(e.name)}'
                            + (f' <span class="mt-meta">({esc(e.line.remarks)})</span>' if e.line.remarks else '') + '</div>' for e in plan.slot_entries(slot))
            rows_html.append(f'<tr><td class="mt-slot">{esc(SLOT_LABELS[slot])}<span class="mt-time">{esc(time_text)}</span></td>'
                             f'<td>{items or "<span class=mt-empty>Nothing</span>"}</td></tr>')
        with st.container(border=True):
            st.markdown(f'<table class="mt-agenda">{"".join(rows_html)}</table>', unsafe_allow_html=True)

        if pending and doses:
            box("tip", f"Waiting for you ({len(pending)})", f"Not in the plan until you tick the box on the Doses screen: {esc(', '.join(pending))}.")
        for what, why in left_out:
            if why == "could not be verified":      # here `what` is the reason the box was not recognised
                box("bad", "Left out: a box I could not recognise", esc(what[0].upper() + what[1:]) + ". It is not in the plan.")
            else:
                box("bad", f"Left out: {what}", esc(why[0].upper() + why[1:]) + ".")
        if review:
            st.markdown(f'<p class="mt-title" style="font-size:1.3rem;margin-top:1rem">To ask your pharmacist ({len(review)})</p>', unsafe_allow_html=True)
            for f in review:
                quote = f'<div class="mt-quote">{esc(f.quote)}</div>' if f.quote else ""
                body = esc(f.text() if not f.quote else f.text().split(": " + chr(34))[0] + ".")
                box("warn", f.title, body + quote + (f'<div class="mt-meta">Source: {source_html(f.source)}</div>' if f.source else ""))
        if info:
            with st.expander(f"More information ({len(info)})"):
                for f in info:
                    st.markdown(f"**{f.title}.** {f.text()}")
                    if f.source:
                        st.markdown(f'<div class="mt-meta">Source: {source_html(f.source)}</div>', unsafe_allow_html=True)
        with st.expander("What was checked, and what was not"):
            ran = ("Checks run: the same active ingredient in two boxes, the same drug group, the expiry date printed in the code, and whether each box matches the schedule"
                   + (", and word-for-word quotes from sections 4.2 and 4.5 of the official leaflets (the quotes stay in Spanish, as AEMPS wrote them)." if plan.smpc_used
                      else ". The official leaflets were NOT consulted (turned off in Settings)."))
            if any(f.kind == "smpc_unavailable" for f in plan.findings):
                ran += " For some medicine a leaflet section could not be checked (see the notes above)."
            st.write(f"{ran} {NOT_A_FULL_CHECK}")
        box("tip", "Remember", "No warning does <b>not</b> mean the plan is safe. This helper schedules what the doctor prescribed; ask a pharmacist about the medicines together.")
        st.write("")
        nav(2, 4, "Next: print or listen", enabled=bool(doses), why_not="The plan is empty. Go back and choose doses.")

    else:
        header(4, "Print, listen, remind", "Take the plan with you: a page for the fridge, a voice that reads it out, or reminders on a phone.")
        if not doses:
            box("warn", "Nothing to print yet", "Go back and confirm at least one medicine.")
        patient = st.text_input("Name of the person (optional, printed at the top of the calendar)")
        with st.expander("Change the reminder times"):
            times = {s: st.time_input(SLOT_LABELS[s], value=pd.to_datetime(DEFAULT_TIMES[s]).time(), key=f"t_{s}").strftime("%H:%M") for s in SLOTS}
        if doses:
            with tempfile.TemporaryDirectory() as tmp:
                pdf_bytes = render_pdf(plan, Path(tmp) / "plan.pdf", patient).read_bytes()
            st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A page to print</p><p class="mt-hint">Large print, with the official picture of each medicine.</p>', unsafe_allow_html=True)
            st.download_button("Download the calendar to print (PDF)", pdf_bytes, "medication_plan.pdf", "application/pdf", type="primary", width="stretch")
            st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Listen to it</p><p class="mt-hint">A voice reads each time of day.</p>', unsafe_allow_html=True)
            if voice.available():
                if st.button("Read the plan aloud", width="stretch"):
                    with tempfile.TemporaryDirectory() as tmp:
                        st.session_state.voice = {slot: path.read_bytes() for slot, path in voice.render_voice(plan, Path(tmp)).items()}
                for slot, audio in st.session_state.get("voice", {}).items():
                    st.markdown(f'<p class="mt-name" style="margin-top:.6rem">{esc(SLOT_LABELS[slot])}</p>', unsafe_allow_html=True)
                    st.audio(audio, format="audio/wav")
            else:
                st.caption("Reading aloud needs an English voice on this computer; none is installed.")
            st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Reminders on a phone</p><p class="mt-hint">Open the file on the phone to add daily reminders to its calendar.</p>', unsafe_allow_html=True)
            st.download_button("Download the phone reminders (.ics)", to_ics(plan, times).encode("utf-8"), "medication_plan.ics", "text/calendar", width="stretch")
        st.write("")
        nav(3, None)
        st.button("Start over with new medicines", on_click=reset_state, key="start_over_end", width="stretch")
