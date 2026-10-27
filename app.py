"""Caregiver app: photos of the packs -> verified packs -> the caregiver's medication sheet -> plan, calendar PDF, voice and .ics.

  .venv-app/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1

Nothing is decided here: the code is read from the pack, the medicine comes from AEMPS CIMA, and every dose is typed or
picked by the caregiver and confirmed line by line. Photos stay on this machine; only CN lookups go to the public CIMA API
(and, with the explicit consent of the caregiver, one image to the Meta API when a model is used).
It also runs inside the 3D room (scripts/start_demo.py), where photos taken with the virtual phone load by themselves.
"""

import base64
import html
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
from medtable.pipeline import make_plan, manual_pack  # noqa: E402
from medtable.plan import DEFAULT_TIMES, NOT_CONFIRMED, SLOT_LABELS, to_ics  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402
from medtable.rules import Pack  # noqa: E402
from medtable.schedule import SLOTS  # noqa: E402
from medtable.smpc import Smpc  # noqa: E402

DOSES = ["0", "1/4", "1/2", "3/4", "1", "1,5", "2", "3", "4"]
DEMO_ITEMS = [("654177", "281231"), ("662025", "270430"), ("715240", "250600"), ("677379", "280131"), ("656012", "271130"), ("100008", "281231")]
COLUMNS = ["medicine", *SLOTS, "remarks", "confirmed", "cn"]
LATEST_PHOTO = Path("data/world_photos/latest.jpg")
LOCAL_PHOTOS = Path("data/cima/images/full")

st.set_page_config(page_title="Medication planner", layout="wide", initial_sidebar_state="collapsed")
EMBEDDED = st.query_params.get("room") == "1"   # inside the 3D room's side panel: narrower layout

CSS = """
<style>
.block-container { padding-top: 1.2rem; max-width: 1100px; }
.mt-title { font-size: 1.7rem; font-weight: 750; margin: 0; }
.mt-lead { color: #55606e; margin: 0 0 .5rem; }
.mt-bar { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 10px; }
.mt-pill { border: 1px solid #d3dae3; border-radius: 999px; padding: 4px 13px; font-size: .86rem; background: #fff; color: #27323f; }
.mt-pill b { font-weight: 700; }
.mt-pill.ok { border-color: #8fd0ad; background: #eaf7f0; }
.mt-pill.warn { border-color: #f0c777; background: #fff6e0; }
.mt-pill.bad { border-color: #eba5a5; background: #fdeeee; }
.mt-step { display: flex; align-items: center; gap: 10px; font-size: 1.3rem; font-weight: 700; margin: 1.6rem 0 .15rem; }
.mt-num { display: inline-flex; width: 1.9rem; height: 1.9rem; border-radius: 50%; background: #1b5e8a; color: #fff; align-items: center; justify-content: center; font-size: 1rem; }
.mt-num.done { background: #1f8a5b; }
.mt-sub { color: #55606e; margin: 0 0 .7rem 2.9rem; font-size: .95rem; }
.mt-chip { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: .76rem; font-weight: 650; margin: 0 4px 4px 0; }
.mt-chip.ok { background: #e1f4ea; color: #145f39; } .mt-chip.warn { background: #fff0cf; color: #7d5200; }
.mt-chip.bad { background: #fde1e1; color: #961c1c; } .mt-chip.grey { background: #e9edf2; color: #3d4752; }
.mt-card { display: flex; gap: 14px; align-items: center; border: 1px solid #e0e5eb; border-radius: 12px; padding: 10px 12px; margin: 0 0 10px; background: #fff; }
.mt-pic { flex: none; width: 112px; height: 84px; object-fit: contain; background: #f6f8fa; border-radius: 8px; }
.mt-card-body { min-width: 0; }
.mt-name { font-weight: 650; line-height: 1.25; margin: 4px 0 6px; font-size: .95rem; }
.mt-meta { color: #5d6875; font-size: .8rem; }
.mt-agenda { width: 100%; border-collapse: collapse; margin: 4px 0 8px; }
.mt-agenda td { padding: 12px 14px; border-bottom: 1px solid #e3e7ec; vertical-align: top; }
.mt-agenda tr:last-child td { border-bottom: none; }
.mt-slot { width: 9.5rem; font-weight: 700; } .mt-time { display: block; color: #6a7580; font-weight: 500; font-size: .82rem; }
.mt-dose { font-size: 1.12rem; font-weight: 700; } .mt-drug { color: #27323f; } .mt-empty { color: #9aa4af; }
.mt-note { border-left: 5px solid #d99a00; background: #fff8e6; padding: 9px 13px; border-radius: 6px; margin: 8px 0; }
.mt-left { border-left: 5px solid #c0392b; background: #fdf1f0; padding: 9px 13px; border-radius: 6px; margin: 8px 0; }
.mt-quote { color: #3d4752; font-style: italic; margin-top: 4px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
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
    for key in ("readings", "manual", "sheet", "sheet_cns", "photos", "unmatched", "sheet_notes", "voice"):
        st.session_state.pop(key, None)


def state_defaults() -> None:
    st.session_state.setdefault("readings", {})  # photo name -> list[Reading]
    st.session_state.setdefault("photos", {})
    st.session_state.setdefault("manual", [])
    st.session_state.setdefault("sheet", pd.DataFrame(columns=COLUMNS))
    st.session_state.setdefault("sheet_cns", set())
    st.session_state.setdefault("room_seen", time.time())  # only room photos taken after the session started load by themselves


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


def card(source, body: str) -> None:
    st.markdown(f'<div class="mt-card">{picture(source)}<div class="mt-card-body">{body}</div></div>', unsafe_allow_html=True)


def sync_sheet(medicines) -> None:
    """Add one empty row per verified pack that is not yet on the sheet; the caregiver only has to fill in the doses."""
    rows = []
    for m in medicines:
        if m.cn not in st.session_state.sheet_cns:
            st.session_state.sheet_cns.add(m.cn)
            rows.append({"medicine": m.name, **dict.fromkeys(SLOTS, "0"), "remarks": "", "confirmed": False, "cn": m.cn})
    if rows:
        st.session_state.sheet = pd.concat([st.session_state.sheet, pd.DataFrame(rows)], ignore_index=True)


def chip(text: str, kind: str = "grey") -> str:
    return f'<span class="mt-chip {kind}">{esc(text)}</span>'


def expiry_chip(expiry: date | None, today: date) -> str:
    if expiry is None:
        return chip("Expiry unknown", "warn")
    if expiry < today:
        return chip(f"Expired {expiry.isoformat()}", "bad")
    if expiry <= today + timedelta(days=30):
        return chip(f"Expires {expiry.isoformat()}", "warn")
    return chip(f"Expires {expiry.isoformat()}", "grey")


def step(number: int, title: str, subtitle: str, done: bool = False) -> None:
    st.markdown(f'<div class="mt-step"><span class="mt-num {"done" if done else ""}">{number}</span>{esc(title)}</div>'
                f'<div class="mt-sub">{esc(subtitle)}</div>', unsafe_allow_html=True)


@st.fragment(run_every="2s")
def watch_room() -> None:
    """Photos taken with the virtual phone in the 3D room load here by themselves."""
    if not LATEST_PHOTO.exists() or LATEST_PHOTO.stat().st_mtime <= st.session_state.room_seen:
        return
    st.session_state.room_seen = LATEST_PHOTO.stat().st_mtime
    image = cv2.imread(str(LATEST_PHOTO))
    if image is not None:
        add_photo(f"room_{time.strftime('%H:%M:%S', time.localtime(LATEST_PHOTO.stat().st_mtime))}", image)
        st.rerun()


state_defaults()

# ---- header -------------------------------------------------------------------------------------------------------------
head_left, head_right = st.columns([5, 1])
head_left.markdown('<p class="mt-title">Medication planner</p><p class="mt-lead">Photograph the packs, copy the doctor\'s schedule, get a printable plan.</p>',
                   unsafe_allow_html=True)
with head_right.popover("Settings"):
    use_smpc = st.toggle("Quote the leaflets (AEMPS SmPC, sections 4.2 and 4.5)", value=True)
    st.caption("When off, only the checks that need no leaflet text run, and the plan says so.")
    if st.button("Start over", type="secondary"):
        reset_state()
        st.rerun()
st.info("A scheduling aid for caregivers. It gives no medical advice and does not replace the doctor or the pharmacist. "
        "Every dose in the plan is one you typed and confirmed.")
summary = st.empty()
watch_room()

# ---- step 1: packs --------------------------------------------------------------------------------------------------------
today = date.today()
step(1, "Photograph the packs", "A pack is identified only by the code printed on it (Data Matrix), checked against AEMPS CIMA. Hold the phone 50 cm or closer.")
tab_room, tab_upload, tab_code = st.tabs(["3D room photo", "Upload photos", "Type a national code"])
with tab_room:
    st.write("In the 3D room use the buttons at the bottom: walk to a table, hold the phone over it, take the photo. "
             "The photo appears here by itself and is read within a few seconds.")
    c1, c2 = st.columns(2)
    if LATEST_PHOTO.exists() and c1.button("Load the latest room photo"):
        image = cv2.imread(str(LATEST_PHOTO))
        if image is None:
            st.error("The latest room photo could not be opened.")
        else:
            add_photo(f"room_{time.strftime('%H:%M:%S', time.localtime(LATEST_PHOTO.stat().st_mtime))}", image)
    if c2.button("Load a demo photo (synthetic codes)"):
        add_photo("demo", synthetic.demo_photo(DEMO_ITEMS))
with tab_upload:
    uploads = st.file_uploader("Photos of the packs (JPG or PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    current = {u.name for u in uploads or []}
    for gone in [n for n in st.session_state.readings if n not in current and n != "demo" and not n.startswith("room_")]:  # a removed upload must not stay in the plan
        st.session_state.readings.pop(gone, None)
        st.session_state.photos.pop(gone, None)
    for upload in uploads or []:
        if upload.name not in st.session_state.readings:
            decoded = cv2.imdecode(np.frombuffer(upload.getvalue(), np.uint8), cv2.IMREAD_COLOR)
            if decoded is None:
                st.error(f"{upload.name}: could not be opened as an image (use JPG or PNG; iPhone HEIC photos must be converted).")
            else:
                add_photo(upload.name, decoded)
with tab_code:
    typed = st.text_input("National code (C.N.) printed on the box", placeholder="848226.9")
    if st.button("Add this pack") and typed:
        pack, problem = manual_pack(typed, resolver())
        if problem:
            st.error(problem)
        elif pack.medicine.cn not in {p.medicine.cn for p in st.session_state.manual}:
            st.session_state.manual.append(pack)

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

if not entries and not st.session_state.manual:
    st.caption("No packs yet. Take a photo in the room, upload one, or type a national code.")
cards = [("ok", r.medicine, r.expiry, r) for r in verified] + [("added", p.medicine, None, None) for p in st.session_state.manual]
per_row = 1 if EMBEDDED else 2
for start in range(0, len(cards), per_row):
    for col, (kind, medicine, expiry, reading) in zip(st.columns(per_row), cards[start:start + per_row]):
        with col:
            card(official_photo(medicine), f'<div class="mt-name">{esc(medicine.name)}</div>'
                 + (chip("Verified by its code", "ok") if kind == "ok" else chip("Added by you (valid national code)", "ok"))
                 + expiry_chip(expiry if kind == "ok" else None, today)
                 + f'<div class="mt-meta">C.N. {esc(medicine.cn)}</div>')
for start in range(0, len(unverified), per_row):
    for col, (name, r) in zip(st.columns(per_row), unverified[start:start + per_row]):
        with col:
            image, crop = st.session_state.photos.get(name), None
            if image is not None and r.bbox:
                x0, y0, x1, y1 = r.bbox
                pad = max(x1 - x0, y1 - y0)
                crop = image[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad]
                crop = crop if crop.size else None
            card(crop, f'<div class="mt-name">Code that could not be verified</div>{chip("Not verified", "bad")}{chip("Left out of the plan", "bad")}'
                 f'<div class="mt-meta">{esc("; ".join(explain_problem(p) for p in r.problems) or "reason unknown")}</div>')
sync_sheet([r.medicine for r in verified] + [p.medicine for p in st.session_state.manual])

with st.expander("A box has no readable code? Find it in the photo and pick it from CIMA"):
    st.write("SAM 3 finds the boxes that have no decoded code. A model only suggests candidates from AEMPS CIMA; "
             "**nothing enters the plan until you confirm one against the official photo.**")
    photos = st.session_state.photos
    if st.button("Find boxes without a code", disabled=not photos):
        found = []
        for name, image in photos.items():
            folder = Path("data/cache/segments") / Path(name.replace(":", "")).stem
            folder.mkdir(parents=True, exist_ok=True)
            photo_path = folder / "photo.png"
            cv2.imwrite(str(photo_path), image)
            try:
                with st.spinner(f"SAM 3 is looking for boxes in {name} (about 30 s)..."):
                    boxes = candidates.segment(photo_path, folder)
            except Exception as exc:  # no GPU, SAM environment missing: typing the national code still works
                st.error(f"SAM 3 could not run ({exc}). You can add packs by national code instead.")
                continue
            codes = [decode.Detection(r.raw, r.bbox, r.method) for r in st.session_state.readings.get(name, [])]
            found += [(name, b) for b in candidates.boxes_without_code(boxes, codes)]
        st.session_state.unmatched = found
    for number, (name, box) in enumerate(st.session_state.get("unmatched", [])[:12]):
        left_col, right_col = st.columns([1, 3])
        left_col.image(str(box.crop), caption=f"Box {number + 1} in {name}", width=160)
        with right_col:
            key = f"proposal_{name}_{box.crop.name}"
            backend = vlm.backend_name()
            ok = st.checkbox("I understand this crop is sent to the Meta API (only if it holds no personal data)", key=f"consent_{key}") if backend == "meta" else True
            if st.button("Suggest candidates", key=f"btn_{key}", disabled=not ok):
                try:
                    with st.spinner("Asking the model and AEMPS CIMA..."):
                        st.session_state[key] = candidates.propose(box.crop, resolver())
                except Exception as exc:  # noqa: BLE001
                    st.error(f"The model could not be reached ({exc}).")
            proposal = st.session_state.get(key)
            if proposal:
                if proposal.note:
                    st.info(proposal.note)
                labels = {f"{c.medicine.name} ({', '.join(c.why) or 'no clear match'})": c for c in proposal.candidates}
                choice = st.radio("Which pack is this?", ["None / I do not know", *labels], key=f"radio_{key}") if labels else None
                shown = list(labels.values())[:3]
                for col, cand in zip(st.columns(max(len(shown), 1)), shown):
                    url = official_photo(cand.medicine)
                    if url:
                        col.image(url, caption=f"{cand.medicine.name[:30]} (official AEMPS photo)", width=120)
                if choice in labels and st.button("Confirm this pack", key=f"ok_{key}"):
                    picked = labels[choice].medicine
                    if picked.cn not in {p.medicine.cn for p in st.session_state.manual}:
                        st.session_state.manual.append(Pack(picked, "confirmed"))
                        st.rerun()

# ---- step 2: sheet --------------------------------------------------------------------------------------------------------
step(2, "Copy the medication sheet", "For each pack, choose the dose for each time of day exactly as the doctor wrote it, then tick Confirmed. "
     "Lines you leave unticked stay out of the plan.")
with st.expander("Read the sheet from a photo (optional)"):
    backend = vlm.backend_name()
    if backend == "meta":
        st.warning("With the Meta model the image LEAVES this computer and goes to the Meta API. Use it only for sheets without personal data "
                   "(no name, ID number or address), or set VLM_BACKEND=local to keep it on this machine.")
    else:
        st.caption("Local model: the image does not leave this computer.")
    sheet_photo = st.file_uploader("Photo of the medication sheet", type=["jpg", "jpeg", "png"], key="sheet_photo")
    consent = st.checkbox("I understand where the image is sent and want the model to read it", key="sheet_consent") if backend == "meta" else True
    if st.button("Read the sheet", disabled=not (sheet_photo and consent)):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / sheet_photo.name
            path.write_bytes(sheet_photo.getvalue())
            try:
                with st.spinner("Reading the sheet..."):
                    read = sheet_reader.read_sheet(path)
            except Exception as exc:  # network, budget cap, server not running: tell the caregiver, keep manual entry available
                st.error(f"The sheet could not be read ({exc}). You can type the schedule by hand.")
            else:
                known = set(st.session_state.sheet["medicine"])
                new = [r for r in read.rows if r["medicine"] not in known]
                skipped = [r["medicine"] for r in read.rows if r["medicine"] in known]
                st.session_state.sheet = pd.concat([st.session_state.sheet, pd.DataFrame(new, columns=COLUMNS)], ignore_index=True)
                st.session_state.sheet_notes = read.problems + (
                    [f"Rows whose name was already in the table were not added: {', '.join(skipped)}. Check the table in case they were different lines."] if skipped else []
                ) + ["Check every row against the sheet: the reading can contain mistakes."]
    for note in st.session_state.get("sheet_notes", []):
        st.warning(note)
extra_doses = sorted({str(v) for slot in SLOTS for v in st.session_state.sheet[slot].dropna()} - set(DOSES))  # misread cells stay visible
dose_col = lambda label: st.column_config.SelectboxColumn(label, options=DOSES + extra_doses, default="0", required=True, width="small")
edited = st.data_editor(
    st.session_state.sheet, num_rows="dynamic", hide_index=True, width="stretch", key="sheet_editor",
    column_config={"medicine": st.column_config.TextColumn("Medicine (as on the sheet)", required=True, width="large"),
                   **{s: dose_col(SLOT_LABELS[s]) for s in SLOTS},
                   "remarks": st.column_config.TextColumn("Remarks (e.g. with meals)", width="medium"),
                   "confirmed": st.column_config.CheckboxColumn("Confirmed", default=False, help="Tick when you have checked this line against the sheet"),
                   "cn": st.column_config.TextColumn("Pack code", disabled=True, width="small", help="The pack on the table this line is tied to (optional)")})
records = [{k: ("" if pd.isna(v) else v) for k, v in row.items()} for row in edited.to_dict("records")]
for record in records:
    record["cn"] = record.get("cn") or None
    record["confirmed"] = bool(record.get("confirmed"))

# ---- plan -------------------------------------------------------------------------------------------------------------------
with st.spinner("Preparing the plan..."):
    result = make_plan(readings, st.session_state.manual, records, smpc_source() if use_smpc else None, today)
plan = result.plan
review = [f for f in plan.findings if f.kind != "unverified_item" and f.severity == "review"]
info = [f for f in plan.findings if f.kind != "unverified_item" and f.severity == "info"]
confirmed_lines = sum(1 for r in records if r["confirmed"])
doses = len(plan.entries)
pending = [what for what, why in plan.not_included if why == NOT_CONFIRMED]      # waiting for the caregiver, not a problem yet
left_out = [(what, why) for what, why in plan.not_included if why != NOT_CONFIRMED]

summary.markdown(
    '<div class="mt-bar">'
    f'<span class="mt-pill {"ok" if verified or st.session_state.manual else ""}">Packs: <b>{len(verified) + len(st.session_state.manual)}</b> verified'
    + (f', <b>{len(unverified)}</b> not verified' if unverified else '') + '</span>'
    f'<span class="mt-pill {"ok" if confirmed_lines else ""}">Sheet: <b>{confirmed_lines}</b> of {len(records)} lines confirmed</span>'
    f'<span class="mt-pill {"ok" if doses else ""}">Plan: <b>{doses}</b> doses</span>'
    f'<span class="mt-pill {"warn" if review else ""}">To review: <b>{len(review)}</b></span>'
    f'<span class="mt-pill {"bad" if left_out else ""}">Left out: <b>{len(left_out)}</b></span>'
    '</div>', unsafe_allow_html=True)

# ---- step 3: review ---------------------------------------------------------------------------------------------------------
step(3, "Review the plan", "This is exactly what will be printed. Check it, and read what was left out and why.", done=bool(doses))
if not doses:
    st.info("Nothing in the plan yet. In step 2, pick the doses and tick Confirmed on at least one line." + (f" Waiting for you: {len(pending)} line(s)." if pending else ""))
rows_html = []
for slot in SLOTS:
    time_text = st.session_state.get(f"t_{slot}", DEFAULT_TIMES[slot])
    time_text = time_text.strftime("%H:%M") if hasattr(time_text, "strftime") else time_text
    items = "".join(f'<div><span class="mt-dose">{esc(e.written())}</span> <span class="mt-drug">{esc(e.name)}</span>'
                    + (f' <span class="mt-meta">({esc(e.line.remarks)})</span>' if e.line.remarks else '') + '</div>' for e in plan.slot_entries(slot))
    rows_html.append(f'<tr><td class="mt-slot">{esc(SLOT_LABELS[slot])}<span class="mt-time">{esc(time_text)}</span></td>'
                     f'<td>{items or "<span class=mt-empty>nothing</span>"}</td></tr>')
with st.container(border=True):
    st.markdown(f'<table class="mt-agenda">{"".join(rows_html)}</table>', unsafe_allow_html=True)

if pending and doses:
    st.caption(f"{len(pending)} sheet line(s) are not confirmed yet and stay out of the plan until you tick Confirmed: {', '.join(pending)}.")
if left_out:
    st.markdown(f"**Left out of the calendar ({len(left_out)})**")
    for what, why in left_out:
        st.markdown(f'<div class="mt-left"><b>{esc(what)}</b><br>{esc(why)}</div>', unsafe_allow_html=True)
if review:
    st.markdown(f"**To review with a pharmacist ({len(review)})**")
    for f in review:
        quote = f'<div class="mt-quote">{esc(f.quote)}</div>' if f.quote else ""
        st.markdown(f'<div class="mt-note"><b>{esc(f.title)}</b><br>{esc(f.text() if not f.quote else f.text().split(": " + chr(34))[0] + ".")}{quote}</div>', unsafe_allow_html=True)
        if f.source:
            st.caption(f"Source: {f.source}")
if info:
    with st.expander(f"More information ({len(info)})"):
        for f in info:
            st.markdown(f"**{f.title}.** {f.text()}")
            if f.source:
                st.caption(f"Source: {f.source}")
ran = ("Checks run: duplicate active ingredient, drug class, expiry read from the code, and match with the sheet"
       + (", and verbatim quotes from sections 4.2 and 4.5 of the leaflets (quotes stay in Spanish, as written by AEMPS)." if plan.smpc_used
          else ". The leaflets were NOT consulted (turned off in Settings)."))
if any(f.kind == "smpc_unavailable" for f in plan.findings):
    ran += " For some medicine a leaflet section could not be checked (see the notes above)."
st.caption(f"{ran} {NOT_A_FULL_CHECK} No warning does not mean the plan is safe.")

# ---- step 4: export ---------------------------------------------------------------------------------------------------------
step(4, "Print, listen, remind", "Download the calendar for the fridge, hear it read aloud, or add the reminders to a phone.", done=False)
patient = st.text_input("Patient's name (optional, printed on the calendar)")
with st.expander("Reminder times"):
    times = {s: st.time_input(SLOT_LABELS[s], value=pd.to_datetime(DEFAULT_TIMES[s]).time(), key=f"t_{s}").strftime("%H:%M") for s in SLOTS}
if doses:
    with tempfile.TemporaryDirectory() as tmp:
        pdf_bytes = render_pdf(plan, Path(tmp) / "plan.pdf", patient).read_bytes()
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download the calendar (PDF)", pdf_bytes, "medication_plan.pdf", "application/pdf", width="stretch")
    c2.download_button("Download the reminders (.ics)", to_ics(plan, times).encode("utf-8"), "medication_plan.ics", "text/calendar", width="stretch")
    if voice.available():
        if c3.button("Read the plan aloud", width="stretch"):
            with tempfile.TemporaryDirectory() as tmp:
                st.session_state.voice = {slot: path.read_bytes() for slot, path in voice.render_voice(plan, Path(tmp)).items()}
        for slot, audio in st.session_state.get("voice", {}).items():
            st.write(SLOT_LABELS[slot])
            st.audio(audio, format="audio/wav")
    else:
        c3.caption("Voice needs an English Windows voice; none is installed here.")
else:
    st.caption("The downloads appear when the plan has at least one dose.")
