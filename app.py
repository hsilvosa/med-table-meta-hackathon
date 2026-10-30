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
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from medtable import boxes, candidates, cima, decode, identify, saved, sheet_reader, synthetic, vlm, voice  # noqa: E402
from medtable.calendar_pdf import render_pdf  # noqa: E402
from medtable.findings import NOT_A_FULL_CHECK, explain_problem  # noqa: E402
from medtable.form import CHOICE_LABELS, CHOICE_VALUES, OTHER, QUICK_NOTES, Row, choice_for, merge_read_rows, sync_pack_rows  # noqa: E402
from medtable.pipeline import make_plan, manual_pack  # noqa: E402
from medtable.plan import DAY_SHORT, DEFAULT_TIMES, NOT_CONFIRMED, SLOT_LABELS, box_days, form_noun, large_amount, to_ics, units_in_pack  # noqa: E402
from medtable.resolve import BUNDLED, Resolver  # noqa: E402
from medtable.rules import Pack  # noqa: E402
from medtable.schedule import ALL_DAYS, SLOTS, dose_number, lines_from_rows  # noqa: E402
from medtable.smpc import Smpc  # noqa: E402

DEMO_ITEMS = [("654177", "281231"), ("662025", "270430"), ("715240", "250600"), ("677379", "280131"), ("656012", "271130"), ("100008", "281231")]
FROM_CAMERA = st.query_params.get("source") == "camera"      # the photos come from the camera page (scripts/serve_camera.py), not from the 3D room
PHOTO_SOURCE = "camera" if FROM_CAMERA else "room"
LATEST_PHOTO = Path("data/camera_photos/latest.jpg" if FROM_CAMERA else "data/world_photos/latest.jpg")
LOCAL_PHOTOS = Path("data/cima/images/full")
STEPS = ["Medicines", "Doses", "Check", "Print and listen"]
SLOT_HINT = {"breakfast": "morning", "lunch": "midday", "dinner": "evening", "bedtime": "before sleep"}

cima.RETRIES, cima.TIMEOUT = 2, 8.0          # a lost connection is reported in seconds; the batch scripts keep the patient defaults
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
[data-testid="stBaseButton-tertiary"] {{ min-height: 2.6rem; padding: .3rem 1.1rem; color: #a02020; border: 1px solid #ecc3c3; background: #fff; }}
[data-testid="stBaseButton-tertiary"] p {{ font-size: 1rem !important; font-weight: 650 !important; color: #a02020 !important; }}
[data-testid="stBaseButton-tertiary"]:hover {{ background: #fdeeee; border-color: #d98a8a; }}
[data-testid="stBaseButton-primary"] {{ background: #1b5e8a; border-color: #1b5e8a; }}
[data-testid="stBaseButton-primary"]:disabled {{ background: #c9d3dd; border-color: #c9d3dd; color: #fff; }}
[data-testid="stButtonGroup"] button {{ min-height: 2.9rem; font-size: 1.1rem; font-weight: 650; }}
[data-testid="stWidgetLabel"] p {{ font-size: 1.05rem; font-weight: 650; color: #1f2933; }}
[data-testid="stCheckbox"] label p {{ font-size: 1.1rem; font-weight: 600; }}
[data-testid="stCheckbox"] label > div:nth-of-type(1) {{ width: 1.9rem; height: 1.9rem; min-width: 1.9rem; border-width: 3px; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: #1b5e8a !important; border-color: #1b5e8a !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: #fff !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] {{ background: #1b5e8a !important; border-color: #1b5e8a !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] p, [data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] span {{ color: #fff !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] {{ min-height: 2.9rem; min-width: 3.4rem; }}
[data-testid="stTabs"] button p {{ font-size: 1.05rem; font-weight: 650; }}
.mt-title {{ font-size: 1.75rem !important; font-weight: 800 !important; margin: .2rem 0 .1rem !important; line-height: 1.2 !important; color: #14202b; }}
.mt-lead {{ font-size: 1.12rem !important; color: #33404d; margin: 0 0 .8rem !important; line-height: 1.5 !important; }}
.mt-steps {{ display: flex; gap: 6px; margin: .2rem 0 1rem; }}
.mt-s {{ flex: 1; text-align: center; font-size: .9rem; color: #5d6875; border-top: 6px solid #d3dae3; padding-top: 6px; line-height: 1.2; }}
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
.mt-brand {{ font-size: .95rem !important; font-weight: 800 !important; color: #1b5e8a; margin: 0 0 .3rem !important; letter-spacing: .02em; }}
.mt-pic.none {{ display: flex; align-items: center; justify-content: center; color: #7d8793; font-size: .8rem; text-align: center; }}
.mt-sum {{ font-size: 1.05rem; line-height: 1.5; margin: 4px 0 0; }}
.mt-sum b {{ font-weight: 800; }}
[data-testid="stProgress"] p {{ font-size: 1.05rem !important; font-weight: 700 !important; }}
.mt-heads {{ color: #6f4800; font-weight: 650; margin-top: 4px; line-height: 1.4; }}
.mt-alert {{ color: #8f1818; font-weight: 700; margin-top: 4px; }}
.mt-hint {{ color: #55606e; font-size: .95rem !important; margin: -4px 0 6px !important; }}
@media (max-width: 560px) {{ .mt-card {{ gap: 10px; align-items: flex-start; }} .mt-pic {{ width: 76px; height: 60px; }} .mt-agenda td {{ padding: 10px 6px; }} .mt-slot {{ width: 6rem; }} }}
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
    st.session_state.setdefault("photo_scale", {})  # kept width / original width, to bring a code's position (in original pixels) into the kept image
    st.session_state.setdefault("manual", [])
    st.session_state.setdefault("removed_cns", set())  # medicines the caregiver took out of the list (6-digit national codes)
    st.session_state.setdefault("removed_raw", set())  # codes that could not be recognised and were dismissed
    st.session_state.setdefault("nocode", {})  # photo name -> regions that look like a box but where no code was read (box in original pixels)
    st.session_state.setdefault("nocode_done", set())  # keys of those the caregiver has dealt with
    st.session_state.setdefault("rows", [])  # list[Row]
    st.session_state.setdefault("patient", "")  # printed on the calendar
    st.session_state.setdefault("plan_notes", "")  # printed in the notes box of the calendar
    st.session_state.setdefault("room_seen", time.time())  # only room photos taken after the session started load by themselves
    st.session_state.setdefault("times", dict(DEFAULT_TIMES))  # reminder times; kept here because a widget forgets its value when its screen is left


def go(step: int) -> None:
    st.session_state.step = step
    st.session_state.scroll_top = True
    st.session_state.pop("undo", None)        # "put it back" is offered on the screen where it was removed, until the next step
    st.session_state.pop("notice", None)
    st.session_state.skip_upload_sync = True      # the file uploader is re-created empty on the next visit to screen 1: that is not the user removing files


def remove_medicine(cn: str, name: str = "") -> None:
    """Take a medicine out of the list, with its sheet row. It comes back with "Undo", if a new photo shows it again or if its code is typed."""
    st.session_state.undo = {"label": name or "the medicine", "cn": cn, "manual": [p for p in st.session_state.manual if p.medicine.cn == cn],
                             "rows": [r for r in st.session_state.rows if r.cn == cn]}
    st.session_state.pop("notice", None)       # its counts would be out of date
    st.session_state.removed_cns.add(cn)
    st.session_state.manual = [p for p in st.session_state.manual if p.medicine.cn != cn]
    st.session_state.rows = [r for r in st.session_state.rows if r.cn != cn]


def dismiss_code(raw: str) -> None:
    st.session_state.undo = {"label": "the box I could not recognise", "raw": raw}
    st.session_state.pop("notice", None)
    st.session_state.removed_raw.add(raw)


def undo_last() -> None:
    """Put back what was removed last, as it was (doses and tick included)."""
    undo = st.session_state.pop("undo", None)
    if not undo:
        return
    if "raw" in undo:
        st.session_state.removed_raw.discard(undo["raw"])
        return
    st.session_state.removed_cns.discard(undo["cn"])
    st.session_state.manual += [p for p in undo["manual"] if p.medicine.cn not in {m.medicine.cn for m in st.session_state.manual}]
    st.session_state.rows += [r for r in undo["rows"] if r.id not in {x.id for x in st.session_state.rows}]


def retry_lookups() -> None:
    """Look the codes up again that were read while the official database could not be reached."""
    for name, rs in st.session_state.readings.items():
        st.session_state.readings[name] = [identify.read_code(decode.Detection(r.raw, r.bbox, r.method), resolver()) if identify.UNREACHABLE in r.problems else r
                                           for r in rs]
    st.session_state.pop("notice", None)


def open_saved(text: str) -> None:
    """Put a saved plan back: the codes are read again against CIMA, the caregiver's choices are restored. Photos are not in the file."""
    try:
        data = saved.load(text)
    except ValueError as exc:
        st.session_state.notice = ("bad", "The plan could not be opened", esc(str(exc)))
        return
    reset_state()
    state_defaults()
    st.session_state.readings["saved plan"] = [identify.read_code(decode.Detection(c, (0, 0, 0, 0), "saved"), resolver()) for c in data["codes"]]
    for cn in data["typed_cns"]:
        pack, problem = manual_pack(cn, resolver())
        if pack:
            st.session_state.manual.append(pack)
    st.session_state.rows = data["rows"]
    st.session_state.patient, st.session_state.plan_notes = data["patient"], data["notes"]
    st.session_state.times.update({s: v for s, v in data["times"].items() if s in SLOTS})
    st.session_state.removed_cns, st.session_state.removed_raw = data["removed_cns"], data["removed_raw"]
    st.session_state.notice = ("ok", "Plan opened", f"Saved on {esc(data['saved'])}. Every box was checked again with the official database. "
                               "Check that the doses still match the doctor's paper, and add a photo of any new box.")


def saved_file() -> str:
    codes = list(dict.fromkeys(r.raw for rs in st.session_state.readings.values() for r in rs))
    return saved.dump(rows=st.session_state.rows, codes=codes, typed_cns=[p.medicine.cn for p in st.session_state.manual], patient=st.session_state.patient,
                      notes=st.session_state.plan_notes, times=st.session_state.times, removed_cns=st.session_state.removed_cns,
                      removed_raw=st.session_state.removed_raw, today=today)


def line_of(row: Row):
    return lines_from_rows([row.as_record()])[0][0]


def days_words(days) -> str:
    return "" if tuple(days) == ALL_DAYS else (", ".join(DAY_SHORT[d] for d in days) + " only" if days else "no day chosen")


def ask_reset() -> None:
    st.session_state.ask_reset = True
    st.session_state.scroll_top = True


def unconfirm(row: Row) -> None:
    """A changed amount needs a fresh tick: the tick says "this matches the doctor's schedule" about the amounts shown when it was given."""
    row.confirmed = False
    st.session_state.pop(row.key("ok"), None)


def count(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def dose_words(dose: str, form: str | None) -> str:
    """'1/2' -> '½ tablet', '2' -> '2 tablets'; an amount typed under Other is shown as typed."""
    singular, plural = form_noun(form)
    value = dose_number(dose)
    return f"{CHOICE_LABELS.get(dose, dose)} {singular if value is not None and value <= 1 else plural}"


def nocode_key(name: str, box: tuple) -> str:
    return f"{name}|{box[0] // 64}|{box[1] // 64}"


def nocode_dealt_with(key: str) -> None:
    st.session_state.nocode_done.add(key)


def remove_photo(name: str) -> None:
    st.session_state.nocode.pop(name, None)
    st.session_state.readings.pop(name, None)
    st.session_state.photos.pop(name, None)
    st.session_state.photo_scale.pop(name, None)


def patient_field(key: str) -> None:
    """The name printed on the calendar. It is asked on the doses screen and again before printing; both edit the same value."""
    def changed() -> None:
        st.session_state.patient = st.session_state[key].strip()
    st.text_input("Who is this plan for? (optional)", value=st.session_state.patient, key=key, on_change=changed, placeholder="For example: Maria Lopez",
                  help="Printed at the top of the calendar. Leave it empty to write the name by hand.")


def page_preview(pdf_path: Path):
    """First page of the PDF as a picture, so the caregiver sees what will be printed. None when the renderer is not installed."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        return document[0].render(scale=1.4).to_pil()
    finally:
        document.close()


MAX_KEPT_WIDTH = 4000


def add_photo(name: str, image: np.ndarray) -> None:
    with st.spinner(f"Reading the codes in {name} (a few seconds)..."):
        st.session_state.readings[name] = identify.identify(image, resolver())     # always the full-resolution photo
    for reading in st.session_state.readings[name]:        # a new photo that shows a removed box again brings it back
        st.session_state.removed_cns.discard(reading.medicine.cn if reading.medicine else "")
        st.session_state.removed_raw.discard(reading.raw)
    st.session_state.nocode[name] = boxes.without_code(boxes.find_boxes(image), [r.bbox for r in st.session_state.readings[name]])      # light finder: see src/medtable/boxes.py
    scale = min(1.0, MAX_KEPT_WIDTH / image.shape[1])        # what is kept for crops and for SAM: a 48 MP photo would take 150 MB of memory
    st.session_state.photos[name] = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else image
    st.session_state.photo_scale[name] = scale
    found = st.session_state.readings[name]
    known = len({r.medicine.cn for r in found if r.status == "verified" and r.medicine})
    unknown = sum(1 for r in found if not (r.status == "verified" and r.medicine))
    missing = len(st.session_state.nocode[name])
    offline = sum(1 for r in found if identify.UNREACHABLE in r.problems)
    if offline:
        st.session_state.notice = ("bad", "No connection to the official database",
                                   f"I read {count(offline, 'code')} but could not check {'it' if offline == 1 else 'them'} with AEMPS CIMA. "
                                   "Check the internet connection, then press <b>Try again</b> below.")
        return
    if not found and not missing:
        st.session_state.notice = ("warn", "I could not read any code in this photo",
                                   "Put the boxes with the printed code facing up, use good light, and take the photo closer (about 30 to 90 cm above the boxes).")
    else:
        parts = [count(known, "medicine") + " recognised"] + ([count(unknown, "box", "boxes") + " I could not recognise"] if unknown else []) \
            + ([count(missing, "box", "boxes") + " where I could not read a code"] if missing else [])
        light = " On a white table I cannot point out boxes without a code: check by eye that every box is in the list." if boxes.light_table(image) else ""
        st.session_state.notice = ("ok" if not unknown and not missing else "warn", "Photo read", esc(", ".join(parts)) + ". The list below shows them." + light)


def official_photo(medicine) -> str | None:
    for kind in ("materialas", "formafarmac"):
        for local in (LOCAL_PHOTOS / kind / f"{medicine.nregistro}.jpg", BUNDLED / "photos" / kind / f"{medicine.nregistro}.jpg"):
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
        return '<div class="mt-pic none">No picture</div>'
    if isinstance(source, str) and source.startswith("http"):
        return f'<img class="mt-pic" src="{esc(source)}">'
    image = cv2.imread(source) if isinstance(source, str) else source
    return f'<img class="mt-pic" src="{data_uri(image)}">' if image is not None else '<div class="mt-pic"></div>'


def card(source, body: str, plain: bool = False) -> None:
    st.markdown(f'<div class="mt-card{" plain" if plain else ""}">{picture(source)}<div>{body}</div></div>', unsafe_allow_html=True)


def box(kind: str, title: str, text: str = "") -> None:
    st.markdown(f'<div class="mt-box {kind}"><b class="t">{esc(title)}</b>{text}</div>', unsafe_allow_html=True)


def what_to_do(reason: str) -> str:
    """One plain next step for the usual reasons a medicine is left out of the plan."""
    if reason == "no pack on the table matches":
        return "Go back to Medicines and add a photo that shows this box, or type the code printed on it."
    if reason.startswith("the pack expired"):
        return "Do not use it. Ask a pharmacist for a new pack."
    if reason.startswith("the pack is on several lines"):
        return "Go back to Doses and keep one line for this medicine."
    if reason.startswith("several packs match"):
        return "Go back to Doses and write the name of the medicine the way it appears on the box."
    if reason.startswith("the strength on the sheet does not match"):
        return "Compare the strength on the box with the doctor's paper and correct the line."
    if reason.startswith("unrecognised dose"):
        return "Go back to Doses and choose the amount with the buttons."
    return ""


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
    st.markdown(f'<p class="mt-brand">Medication planner</p><div class="mt-steps">{cells}</div><p class="mt-title">{esc(title)}</p><p class="mt-lead">{lead}</p>', unsafe_allow_html=True)


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
        add_photo(f"{PHOTO_SOURCE}_{time.strftime('%H:%M:%S', time.localtime(LATEST_PHOTO.stat().st_mtime))}", image)
        st.session_state.step = 1
        st.rerun()


state_defaults()
today = date.today()

# ---- the readings, the sheet rows and the plan are computed on every screen (cheap, cached lookups) -----------------------
seen_raw: set[str] = set()
entries = []          # (photo name, reading), one per physical pack (same code text = same pack), without what the caregiver removed
for name, rs in st.session_state.readings.items():
    for r in rs:
        removed = (r.medicine.cn in st.session_state.removed_cns) if r.medicine else (r.raw in st.session_state.removed_raw)
        if r.raw not in seen_raw and not removed:
            seen_raw.add(r.raw)
            entries.append((name, r))
readings = [r for _, r in entries]
verified = [r for r in readings if r.status == "verified" and r.medicine]
unverified = [(n, r) for n, r in entries if r.status != "verified" or not r.medicine]
boxes_of: dict[str, list] = {}       # national code -> the readings of every box of that medicine (two boxes of one medicine are one medicine)
for r in verified:
    boxes_of.setdefault(r.medicine.cn, []).append(r)
typed_only = [p for p in st.session_state.manual if p.medicine.cn not in boxes_of]
medicines = [rs[0].medicine for rs in boxes_of.values()] + [p.medicine for p in typed_only]
expired_cns = {cn for cn, rs in boxes_of.items() if all(r.expiry and r.expiry < today for r in rs)}


def shared_ingredient(medicine) -> list[str]:
    """The other medicines in the list with an active ingredient in common (a fact from CIMA, shown so the caregiver can ask)."""
    mine = {a.strip().lower() for a in medicine.active_ingredients}
    return [m.name for m in medicines if m.cn != medicine.cn and mine & {a.strip().lower() for a in m.active_ingredients}]


def medicine_card(medicine, chips: str, rs: list) -> None:
    body = f'<div class="mt-name">{esc(medicine.name)}</div>' + chips
    if medicine.active_ingredients:
        body += f'<div class="mt-meta">Active ingredient: {esc(", ".join(a.capitalize() for a in medicine.active_ingredients))}</div>'
    old = [r for r in rs if r.expiry and r.expiry < today]
    if old and len(old) == len(rs):
        body += '<div class="mt-alert">This box has expired. Do not use it: it will be left out of the plan.</div>'
    elif old:
        body += f'<div class="mt-alert">{len(old)} of {len(rs)} boxes have expired. Do not use the expired one.</div>'
    if (others := shared_ingredient(medicine)):
        body += f'<div class="mt-heads">Same active ingredient as: {esc("; ".join(others))}. The plan lists it for the pharmacist.</div>'
    card(official_photo(medicine), body, plain=True)
sync_pack_rows(st.session_state.rows, medicines)
rows: list[Row] = st.session_state.rows

# ---- settings (small, out of the way) ---------------------------------------------------------------------------------------
with st.popover("Settings"):
    st.toggle("Larger text", key="large_text")
    use_smpc = st.toggle("Quote the official leaflets (AEMPS) in the notes", value=True)
    st.caption("When off, only the checks that need no leaflet text run, and the plan says so.")
    st.button("Start over", on_click=ask_reset, key="start_over", width="stretch")

if st.session_state.get("ask_reset"):
    box("warn", "Start over?", "This deletes the medicines, the doses and the notes of this plan. It cannot be undone.")
    no, yes = st.columns(2)       # the safe answer first and in colour
    no.button("No, keep my work", on_click=lambda: st.session_state.pop("ask_reset", None), type="primary", key="reset_no", width="stretch")
    yes.button("Yes, delete everything", on_click=reset_state, key="reset_yes", width="stretch")

if st.session_state.get("scroll_top"):
    st.session_state.scroll_top = False
    st.iframe("<script>const m=window.parent.document.querySelector('[data-testid=\"stMain\"]'); if(m) m.scrollTo(0,0);</script>", height=1)   # fixed text, no user input
watch_room()
step = st.session_state.step

# =============================================================================================================================
# Screen 1: the medicines
# =============================================================================================================================
if step == 1:
    header(1, "Show me the medicines", "Take a photo of the medicine boxes on the table. I read the code printed on each box.")
    st.info("This is a helper for planning. It gives no medical advice and does not replace the doctor or the pharmacist.")
    if EMBEDDED:
        if FROM_CAMERA:
            box("tip", "Take the photo with the camera", "Point the camera at the boxes and press the red <b>Take photo</b> button. The photo appears here by itself in a few seconds.")
        else:
            box("tip", "Take the photo in the room", "Press the red <b>Take photo</b> button on the left of the room. The photo appears here by itself in a few seconds.")
        add_area = st.expander("Add a medicine another way")
    else:
        box("tip", "For a good photo", "Put the boxes on a table with the printed codes facing up, and hold the phone about 90 cm (3 feet) above them or closer.")
        add_area = st.container()
    with add_area:
        tab_upload, tab_code, tab_saved, tab_demo = st.tabs(["Upload a photo", "Type a code", "Open a saved plan", "Demo photos"])
        with tab_saved:
            st.write("A plan saved before with **Save this plan** (on the last screen). The boxes are checked again with the official database.")
            saved_upload = st.file_uploader("Choose the saved plan (a .json file)", type=["json"], key="saved_upload")
            if saved_upload is not None and st.session_state.get("opened_file") != saved_upload.file_id:
                opened = saved_upload.file_id
                open_saved(saved_upload.getvalue().decode("utf-8", "replace"))
                st.session_state.opened_file = opened
                st.rerun()
        with tab_demo:
            st.write("Photos made for trying the tool. They contain no real medication or patient.")
            c1, c2 = st.columns(2)
            if LATEST_PHOTO.exists() and c1.button(f"Load the latest {PHOTO_SOURCE} photo", width="stretch"):
                image = cv2.imread(str(LATEST_PHOTO))
                if image is None:
                    st.error(f"The latest {PHOTO_SOURCE} photo could not be opened.")
                else:
                    add_photo(f"{PHOTO_SOURCE}_{time.strftime('%H:%M:%S', time.localtime(LATEST_PHOTO.stat().st_mtime))}", image)
                    st.rerun()
            if c2.button("Load a demo photo", width="stretch"):
                add_photo("demo", synthetic.demo_photo(DEMO_ITEMS))
                st.rerun()
        with tab_upload:
            uploads = st.file_uploader("Choose a photo of the boxes (JPG or PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
            current = {u.name for u in uploads or []}
            previous = st.session_state.get("seen_uploads", set())
            if st.session_state.pop("skip_upload_sync", False):
                previous = current      # a freshly created, empty uploader after a screen change is not a removal
            for gone in previous - current:  # a file the user removed from the uploader must not stay in the plan
                remove_photo(gone)
            st.session_state.seen_uploads = set(current)
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
            st.write("Every box has a national code (C.N.) printed on it: six or seven digits, for example 848226.9.")
            with st.form("type_code", clear_on_submit=True, border=False):
                typed = st.text_input("The code on the box", placeholder="848226.9", key="typed_code")
                submitted = st.form_submit_button("Add this medicine", width="stretch")
            if submitted and typed.strip():
                pack, problem = manual_pack(typed, resolver())
                if problem:
                    st.error(problem)
                elif pack.medicine.cn in {m.cn for m in medicines}:
                    st.info(f"{pack.medicine.name} is already in the list.")
                else:
                    st.session_state.removed_cns.discard(pack.medicine.cn)
                    if pack.medicine.cn not in {p.medicine.cn for p in st.session_state.manual}:
                        st.session_state.manual.append(pack)
                    st.session_state.notice = ("ok", "Added", esc(pack.medicine.name) + ". It is in the list below.")
                    st.rerun()

    if st.session_state.photos:
        with st.expander(f"Photos used so far ({len(st.session_state.photos)})"):
            for photo_name in list(st.session_state.photos):
                left, right = st.columns([3, 1])
                left.write(photo_name)
                right.button("Remove", key=f"rm_{photo_name}", on_click=remove_photo, args=(photo_name,), width="stretch")
    if (notice := st.session_state.get("notice")):
        box(*notice)
    st.markdown(f'<p class="mt-title" style="font-size:1.35rem;margin-top:1.2rem">Medicines found: {len(medicines)}</p>', unsafe_allow_html=True)
    if (undo := st.session_state.get("undo")):
        box("ok", f"Removed: {undo['label']}", "Removed by mistake? Press the button to put it back.")
        st.button("Undo: put it back", on_click=undo_last, key="undo_btn", type="primary")

    if not entries and not st.session_state.manual:
        box("tip", "Nothing yet", "Add a photo or type a code above. The medicines I recognise will appear here.")
    for cn, rs in boxes_of.items():
        expiries = sorted({r.expiry for r in rs if r.expiry})
        chips = chip("Recognised from its code", "ok") + (chip(f"{len(rs)} boxes", "grey") if len(rs) > 1 else "") \
            + ("".join(expiry_chip(e, today) for e in expiries) if expiries else expiry_chip(None, today))
        with st.container(border=True):
            medicine_card(rs[0].medicine, chips, rs)
            st.button("Remove this medicine", key=f"del_{cn}", on_click=remove_medicine, args=(cn, rs[0].medicine.name), type="tertiary")
    for pack in typed_only:
        with st.container(border=True):
            medicine_card(pack.medicine, chip("Added by you", "ok"), [])
            st.button("Remove this medicine", key=f"del_{pack.medicine.cn}", on_click=remove_medicine, args=(pack.medicine.cn, pack.medicine.name), type="tertiary")
    for name, r in unverified:
        image, crop = st.session_state.photos.get(name), None
        if image is not None and r.bbox:
            x0, y0, x1, y1 = (int(v * st.session_state.photo_scale.get(name, 1.0)) for v in r.bbox)
            pad = max(x1 - x0, y1 - y0)
            crop = image[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad]
            crop = crop if crop.size else None
        with st.container(border=True):
            card(crop, f'<div class="mt-name">A box I could not recognise</div>{chip("Not in the plan", "bad")}'
                 f'<div class="mt-meta">{esc("; ".join(explain_problem(p) for p in r.problems) or "reason unknown")}</div>', plain=True)
            if identify.UNREACHABLE in r.problems:
                st.button("Try again", key=f"retry_{r.raw}", on_click=retry_lookups, type="primary")
            st.button("Dismiss", key=f"dismiss_{r.raw}", on_click=dismiss_code, args=(r.raw,), type="tertiary")
    for name, regions in st.session_state.nocode.items():
        for region in regions:
            key = nocode_key(name, region)
            if key in st.session_state.nocode_done:
                continue
            image, crop = st.session_state.photos.get(name), None
            if image is not None:
                x0, y0, x1, y1 = (int(v * st.session_state.photo_scale.get(name, 1.0)) for v in region)
                crop = image[max(y0 - 10, 0):y1 + 10, max(x0 - 10, 0):x1 + 10]
                crop = crop if crop.size else None
            with st.container(border=True):
                card(crop, f'<div class="mt-name">A box where I could not read a code</div>{chip("Not in the plan yet", "warn")}'
                     '<div class="mt-meta">Take a close-up photo of this box (about 30 cm above it, the printed code facing up), or type the code printed on it. '
                     + (('Bring the camera closer to this box, then press <b>Take photo</b>. ' if FROM_CAMERA else 'In the room, press <b>Close-up of the box with no code</b> on the left, then <b>Take photo</b>. ') if EMBEDDED else "")
                     + 'I may be wrong: it can also be something that is not a medicine.</div>', plain=True)
                st.button("Done: I added it or it is not a medicine", key=f"nocode_{key}", on_click=nocode_dealt_with, args=(key,), type="tertiary")
    if entries or st.session_state.manual:
        st.caption("Is a box missing? Take another photo that shows it close up with its code facing up, or type its code. Wrong box? Remove it.")

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
                factor = st.session_state.photo_scale.get(name, 1.0)
                codes = [decode.Detection(r.raw, tuple(int(v * factor) for v in r.bbox), r.method) for r in st.session_state.readings.get(name, [])]
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
                        st.session_state[key] = candidates.propose(found_box.crop, resolver(), consent=ok is True)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"The model could not be reached ({exc}).")
            proposal = st.session_state.get(key)
            if proposal:
                if proposal.note:
                    st.info(proposal.note)
                labels = {f"**{c.medicine.name}**  \n{' · '.join(c.why) or 'no clear match'}": c for c in proposal.candidates}
                choice = st.radio("Which medicine is this?", ["None of these / I do not know", *labels], key=f"radio_{key}") if labels else None
                shown = list(labels.values())[:3]
                for col, cand in zip(st.columns(max(len(shown), 1)), shown):
                    url = official_photo(cand.medicine)
                    if url:
                        col.image(url, caption=f"{cand.medicine.name[:30]} (official picture)", width=120)
                if choice in labels and st.button("Yes, this is the medicine", key=f"ok_{key}", type="primary"):
                    picked = labels[choice].medicine
                    if picked.cn not in {p.medicine.cn for p in st.session_state.manual}:
                        st.session_state.removed_cns.discard(picked.cn)
                        st.session_state.manual.append(Pack(picked, "confirmed"))
                        st.rerun()
    st.write("")
    nav(None, 2, "Next: choose the doses", enabled=bool(medicines), why_not="Add at least one medicine to continue.")

# =============================================================================================================================
# Screen 2: the doses
# =============================================================================================================================
elif step == 2:
    header(2, "Choose the doses",
           "For each medicine, choose <b>how many to take</b> at each time of day, as written on the doctor's paper. "
           "Then tick the box under it. I never choose an amount for you, and medicines that are not ticked stay out of the plan.")
    ready = sum(1 for r in rows if r.confirmed and r.has_dose)
    if rows:
        st.progress(ready / len(rows), text=f"{ready} of {count(len(rows), 'medicine')} ready for the plan")
    patient_field("patient_step2")
    with st.expander("Have a photo of the doctor's schedule? Let the computer copy it (optional)"):
        backend = vlm.backend_name()
        if backend == "meta":
            st.warning("The photo LEAVES this computer and goes to the Meta API. Use it only for a sheet without personal data "
                       "(no name, ID number or address). To keep it on this computer, whoever installed the tool can switch it to the offline model (VLM_BACKEND=local).")
        else:
            st.caption("Local model: the picture does not leave this computer.")
        sheet_photo = st.file_uploader("Photo of the schedule", type=["jpg", "jpeg", "png"], key="sheet_photo")
        consent = st.checkbox("I understand where the picture is sent and want the computer to read it", key="sheet_consent") if backend == "meta" else True
        sources = []
        if sheet_photo:
            sources.append(("Read the schedule", sheet_photo.name, sheet_photo.getvalue()))
        if LATEST_PHOTO.exists():
            sources.append((f"Read the latest {PHOTO_SOURCE} photo as the schedule", f"{PHOTO_SOURCE}_schedule.jpg", LATEST_PHOTO.read_bytes() if consent else b""))
        for label, file_name, content in sources:
            if st.button(label, disabled=not consent, width="stretch", key=f"read_{file_name}"):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / file_name
                    path.write_bytes(content)
                    try:
                        with st.spinner("Reading the schedule..."):
                            read = sheet_reader.read_sheet(path, consent=consent is True)
                    except Exception as exc:  # network, budget cap, server not running: tell the caregiver, keep manual entry available
                        st.error(f"The schedule could not be read ({exc}). You can choose the doses by hand below.")
                    else:
                        packs_now = [Pack(m, "verified") for m in medicines]
                        changed, merge_notes = merge_read_rows(rows, read.rows, packs_now)      # bumps `rev`, so the buttons show what was read
                        st.session_state.sheet_notes = read.problems + merge_notes + ["Check every medicine against the paper: a computer reading can contain mistakes."]
        for note in st.session_state.get("sheet_notes", []):
            st.warning(note)

    def set_dose(row: Row, slot: str) -> None:
        picked = st.session_state[row.key("dose", slot)]
        if picked is None:      # clicking the selected button again would clear it: keep the choice
            st.session_state[row.key("dose", slot)] = choice_for(row.doses[slot])
            return
        if picked != OTHER:
            row.doses[slot] = picked
        elif choice_for(row.doses[slot]) != OTHER:
            row.doses[slot] = ""        # "Other" with nothing typed yet: the plan reports it instead of guessing
        unconfirm(row)

    def set_other(row: Row, slot: str) -> None:
        row.doses[slot] = st.session_state[row.key("other", slot)].strip()
        unconfirm(row)

    def set_often(row: Row) -> None:
        picked = st.session_state[row.key("often")]
        if picked is None:
            return
        row.days = list(ALL_DAYS) if picked == "every" else []        # "some days": the caregiver ticks them, none is assumed
        unconfirm(row)

    def set_days(row: Row) -> None:
        row.days = sorted(st.session_state[row.key("days")] or [])
        unconfirm(row)

    def set_quick(row: Row) -> None:
        row.quick = list(st.session_state[row.key("quick")] or [])

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
            if row.cn in expired_cns:
                body += '<div class="mt-alert">The box has expired: this medicine will be left out of the plan until there is a new box.</div>'
            if row.sheet_name and row.sheet_name != row.medicine:
                body += f'<div class="mt-meta">The schedule says: {esc(row.sheet_name)}</div>'
            form = pack.form if pack else None
            if (big := large_amount(line_of(row))):
                body += f'<div class="mt-alert">Please check: {big:g} a day is more than usual for one medicine. Compare it with the doctor\'s paper.</div>'
            if row.confirmed and row.has_dose:          # done: a short summary instead of 28 buttons, so the list stays short
                taken = [f"{esc(SLOT_LABELS[s])}: <b>{esc(dose_words(row.doses[s], form))}</b>" for s in SLOTS if dose_number(row.doses[s]) != 0]
                if (when := days_words(row.days)):
                    taken.append(f"<b>{esc(when)}</b>")
                body += chip("Ready for the plan", "ok") + f'<div class="mt-sum">{" &middot; ".join(taken)}</div>' \
                    + (f'<div class="mt-meta">Note: {esc(row.note)}</div>' if row.note else "")
                card(official_photo(pack) if pack else None, body, plain=True)
                st.button("Change the amounts", key=f"edit_{row.id}", on_click=unconfirm, args=(row,))
                continue
            card(official_photo(pack) if pack else None, body, plain=True)
            plural = form_noun(form)[1]
            for slot in SLOTS:
                question = f"how many {plural}?" if plural != "doses" else "how many?"
                st.segmented_control(f"{SLOT_LABELS[slot]} ({SLOT_HINT[slot]}): {question}", CHOICE_VALUES + [OTHER], format_func=CHOICE_LABELS.get,
                                     default=choice_for(row.doses[slot]), key=row.key("dose", slot), on_change=set_dose, args=(row, slot))
                if choice_for(row.doses[slot]) == OTHER:
                    st.text_input("Type the amount (for example 4 or 2,5)", value=row.doses[slot], key=row.key("other", slot), on_change=set_other, args=(row, slot))
            every = tuple(row.days) == ALL_DAYS
            st.segmented_control("Which days?", ["every", "some"], format_func={"every": "Every day", "some": "Only some days of the week"}.get,
                                 default="every" if every else "some", key=row.key("often"), on_change=set_often, args=(row,))
            if not every:
                st.pills("Tick the days it is taken", list(range(7)), format_func=lambda d: DAY_SHORT[d], selection_mode="multi", default=list(row.days),
                         key=row.key("days"), on_change=set_days, args=(row,))
                if not row.days:
                    st.markdown('<p class="mt-hint">Tick at least one day.</p>', unsafe_allow_html=True)
            with st.expander("Add a note to print next to this medicine (optional)", expanded=bool(row.note)):
                st.pills("Tick what the doctor's paper says", QUICK_NOTES, selection_mode="multi", default=row.quick, key=row.key("quick"), on_change=set_quick, args=(row,))
                st.text_input("Anything else (for example: white tablet, keep in the fridge)", value=row.remarks, key=row.key("remarks"), on_change=set_field,
                              args=(row, "remarks", row.key("remarks")))
            st.checkbox("Yes, this matches the doctor's schedule", value=row.confirmed, key=row.key("ok"), on_change=set_field, args=(row, "confirmed", row.key("ok")))
            if row.confirmed and row.has_dose:
                st.markdown(chip("Will be in the plan", "ok"), unsafe_allow_html=True)
            elif row.confirmed:
                st.markdown(chip("Ticked, but every amount is None", "warn"), unsafe_allow_html=True)
            else:
                st.markdown(chip("Not in the plan yet: choose the amounts, then tick the box", "grey"), unsafe_allow_html=True)

    with st.expander("A medicine on the schedule that has no box on the table"):
        st.write("Type its name as written on the schedule. The plan will list it as \"on the schedule but not on the table\".")
        def add_line() -> None:      # a callback: a widget's value can only be changed before the widget is created in a run
            name = st.session_state.extra_name.strip()
            if name:
                st.session_state.rows.append(Row(f"hand{len(st.session_state.rows) + 1}", name))
                st.session_state.extra_name = ""

        extra = st.text_input("Name on the schedule", key="extra_name")
        st.button("Add this line", on_click=add_line, disabled=not extra.strip(), width="stretch")
    st.write("")
    nav(1, 3, "Next: see the plan", enabled=bool(rows), why_not="There are no medicines yet. Go back and add one.")
    st.caption(f"{ready} of {count(len(rows), 'medicine')} will be in the plan.")

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
        if st.session_state.patient:
            st.markdown(f'<p class="mt-lead">Plan for <b>{esc(st.session_state.patient)}</b></p>', unsafe_allow_html=True)
        rows_html = []
        for slot in SLOTS:
            time_text = st.session_state.times[slot]
            items = "".join(f'<div style="margin-bottom:6px"><span class="mt-dose">{esc(e.written())}</span> of {esc(e.name)}'
                            + (f' <b>({esc(e.days_text())})</b>' if e.days_text() else '')
                            + (f' <span class="mt-meta">({esc(e.line.remarks)})</span>' if e.line.remarks else '') + '</div>' for e in plan.slot_entries(slot))
            rows_html.append(f'<tr><td class="mt-slot">{esc(SLOT_LABELS[slot])}<span class="mt-time">{esc(time_text)}</span></td>'
                             f'<td>{items or "<span class=mt-empty>Nothing</span>"}</td></tr>')
        with st.container(border=True):
            st.markdown(f'<table class="mt-agenda">{"".join(rows_html)}</table>', unsafe_allow_html=True)

        lines_in = {}
        for e in plan.entries:
            lines_in.setdefault(e.pack.medicine.cn, (e.pack.medicine, e.line))
        for medicine, line in lines_in.values():
            if (big := large_amount(line)):
                box("warn", f"Please check the amount of {medicine.name}", f"{big:g} a day is more than usual for one medicine. "
                    "It is in the plan as you chose it: compare it with the doctor's paper.")
        lasting = []
        for medicine, line in lines_in.values():
            units = units_in_pack(medicine.presentation)
            if (days_left := box_days(units, line)):
                lasting.append(f"<li><b>{esc(medicine.name)}</b>: a full box of {units} lasts about <b>{days_left} days</b> at these amounts.</li>")
        if lasting:
            box("tip", "How long a box lasts", f'<ul style="margin:.3rem 0 0 1.1rem;padding:0">{"".join(lasting)}</ul>'
                '<div class="mt-meta">Counted from the pack size listed by AEMPS CIMA, for a full box. Ask for the next box a week before.</div>')
        if pending and doses:
            box("tip", f"Waiting for you ({len(pending)})", f"Not in the plan until you tick the box on the Doses screen: {esc(', '.join(pending))}.")
        for what, why in left_out:
            if why == "could not be verified":      # here `what` is the reason the box was not recognised
                box("bad", "Left out: a box I could not recognise", esc(what[0].upper() + what[1:]) + ". It is not in the plan.")
            else:
                box("bad", f"Left out: {what}", esc(why[0].upper() + why[1:]) + "." + (f" <b>What to do:</b> {esc(todo)}" if (todo := what_to_do(why)) else ""))
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
        with st.container(border=True):
            st.markdown('<p class="mt-name">Before you print</p><p class="mt-hint">Both are optional. Anything left empty is printed as lines to write on by hand.</p>', unsafe_allow_html=True)
            patient_field("patient_step4")
            st.text_area("Notes for the whole plan (for example: doctor's phone number, allergies)", value=st.session_state.plan_notes, key="plan_notes_box", height=110,
                         on_change=lambda: st.session_state.update(plan_notes=st.session_state.plan_notes_box.strip()))
            def set_time(slot: str) -> None:
                st.session_state.times[slot] = st.session_state[f"t_{slot}"].strftime("%H:%M")

            with st.expander("Change the reminder times"):
                for s in SLOTS:
                    st.time_input(SLOT_LABELS[s], value=datetime.strptime(st.session_state.times[s], "%H:%M").time(), key=f"t_{s}", on_change=set_time, args=(s,))
            times = dict(st.session_state.times)
        if doses:
            with tempfile.TemporaryDirectory() as tmp:
                pdf_path = render_pdf(plan, Path(tmp) / "plan.pdf", st.session_state.patient, notes=st.session_state.plan_notes, times=times)
                pdf_bytes = pdf_path.read_bytes()
                preview = page_preview(pdf_path)
            if preview is not None:
                st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">This is the page you will print</p>', unsafe_allow_html=True)
                st.image(preview, width="stretch")
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
            st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Continue later</p><p class="mt-hint">'
                        'Saves the medicines and the doses (not the photos) in a small file. Open it next month on the first screen.</p>', unsafe_allow_html=True)
            st.download_button("Save this plan to continue later", saved_file().encode("utf-8"), "medication_plan_saved.json", "application/json", width="stretch")
            st.download_button("Download the phone reminders (.ics)", to_ics(plan, times).encode("utf-8"), "medication_plan.ics", "text/calendar", width="stretch")
        st.write("")
        nav(3, None)
        st.button("Start over with new medicines", on_click=ask_reset, key="start_over_end", width="stretch")
