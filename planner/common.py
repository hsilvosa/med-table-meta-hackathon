"""Shared parts of the planner: page settings, session state and the actions that change it, and small rendering helpers."""

import base64
import os
import copy
import html
import re
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from medtable import boxes, cima, decode, identify, saved
from medtable.form import CHOICE_LABELS, Row
from medtable.i18n import tr
from medtable.pipeline import manual_pack
from medtable.plan import DAY_SHORT, DEFAULT_TIMES, form_noun
from medtable.resolve import BUNDLED, Resolver
from medtable.schedule import ALL_DAYS, SLOTS, dose_number, lines_from_rows
from medtable.smpc import Smpc

LOCAL_PHOTOS = Path("data/cima/images/full")
STEPS = ["Medicines", "Doses", "Check", "Print and listen"]
SLOT_HINT = {"breakfast": "morning", "lunch": "midday", "dinner": "evening", "bedtime": "before sleep"}
cima.RETRIES, cima.TIMEOUT = 2, 8.0          # a lost connection is reported in seconds; the batch scripts keep the patient defaults
esc = html.escape


def from_camera() -> bool:
    """The photos come from the camera page (scripts/serve_camera.py), not from the 3D room."""
    return st.query_params.get("source") == "camera"


def photo_source() -> str:
    return "camera" if from_camera() else "room"


def public_demo() -> bool:
    """The online demo (Hugging Face Space): shared server, so no model calls, no SAM, and each visitor sees only their own room photos."""
    return os.environ.get("PUBLIC_DEMO") == "1"


def session_id() -> str | None:
    """The room's visitor id, passed by the 3D room in the planner's address (?session=...)."""
    value = st.query_params.get("session", "")
    return value if re.fullmatch(r"[a-z0-9-]{8,40}", value or "") else None


def latest_photo() -> Path:
    if public_demo():           # only the photos taken by this visitor's own room
        return Path("data/world_photos") / (session_id() or "none") / "latest.jpg"
    return Path("data/camera_photos/latest.jpg" if from_camera() else "data/world_photos/latest.jpg")


def embedded() -> bool:
    """Inside the 3D room's side panel: narrower layout."""
    return st.query_params.get("room") == "1"

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
        if key not in ("large_text", "lang"):
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
    st.session_state.undo = {"label": name or tr("the medicine"), "cn": cn, "manual": [p for p in st.session_state.manual if p.medicine.cn == cn],
                             "rows": [r for r in st.session_state.rows if r.cn == cn]}
    st.session_state.pop("notice", None)       # its counts would be out of date
    st.session_state.removed_cns.add(cn)
    st.session_state.manual = [p for p in st.session_state.manual if p.medicine.cn != cn]
    st.session_state.rows = [r for r in st.session_state.rows if r.cn != cn]


def dismiss_code(raw: str) -> None:
    st.session_state.undo = {"label": tr("the unrecognised box"), "raw": raw}
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
        st.session_state.notice = ("bad", tr("The plan could not be opened"), esc(str(exc)))
        return
    reset_state()
    state_defaults()
    st.session_state.readings["saved plan"] = [identify.read_code(decode.Detection(c, (0, 0, 0, 0), "saved"), resolver()) for c in data["codes"]]
    for cn in data["typed_cns"]:
        pack, problem = manual_pack(cn, resolver())
        if pack:
            st.session_state.manual.append(pack)
    st.session_state.rows = data["rows"]
    st.session_state.baseline = {"saved": data["saved"], "rows": copy.deepcopy(data["rows"])}      # to show what changed since then
    st.session_state.patient, st.session_state.plan_notes = data["patient"], data["notes"]
    st.session_state.times.update({s: v for s, v in data["times"].items() if s in SLOTS})
    st.session_state.removed_cns, st.session_state.removed_raw = data["removed_cns"], data["removed_raw"]
    st.session_state.notice = ("ok", tr("Plan opened"), tr("Saved on {x0}. Every box was checked again with the official database. Check that the doses still match the doctor's paper, and add a photo of any new box.", x0=esc(data['saved'])))


def saved_file() -> str:
    codes = list(dict.fromkeys(r.raw for rs in st.session_state.readings.values() for r in rs))
    return saved.dump(rows=st.session_state.rows, codes=codes, typed_cns=[p.medicine.cn for p in st.session_state.manual], patient=st.session_state.patient,
                      notes=st.session_state.plan_notes, times=st.session_state.times, removed_cns=st.session_state.removed_cns,
                      removed_raw=st.session_state.removed_raw, today=date.today())


def line_of(row: Row):
    return lines_from_rows([row.as_record()])[0][0]


def days_words(days) -> str:
    return "" if tuple(days) == ALL_DAYS else (", ".join(tr(DAY_SHORT[d]) for d in days) + tr(" only") if days else tr("no day chosen"))


def ask_reset() -> None:
    st.session_state.ask_reset = True
    st.session_state.scroll_top = True


def unconfirm(row: Row) -> None:
    """A changed amount needs a fresh tick: the tick says "this matches the doctor's schedule" about the amounts shown when it was given."""
    row.confirmed = False
    st.session_state.pop(row.key("ok"), None)


def count(n: int, one: str, many: str = "") -> str:
    return f"{n} {tr(one) if n == 1 else tr(many or one + 's')}"


def dose_words(dose: str, form: str | None) -> str:
    """'1/2' -> '½ tablet', '2' -> '2 tablets'; an amount typed under Other is shown as typed."""
    singular, plural = form_noun(form)
    value = dose_number(dose)
    return f"{CHOICE_LABELS.get(dose, dose)} {tr(singular) if value is not None and value <= 1 else tr(plural)}"


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
    st.text_input(tr("Who is this plan for? (optional)"), value=st.session_state.patient, key=key, on_change=changed, placeholder=tr("For example: Maria Lopez"),
                  help=tr("Printed at the top of the calendar. Leave it empty to write the name by hand."))


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
    with st.spinner(tr('Reading the codes in {name} (a few seconds)...', name=name)):
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
        st.session_state.notice = ("bad", tr("No connection to the official database"),
                                   tr('{x0} read, but {x1} could not be checked with AEMPS CIMA. Check the internet connection, then press <b>Try again</b> below.', x0=count(offline, 'code'), x1='it' if offline == 1 else 'them'))
        return
    if not found and not missing:
        st.session_state.notice = ("warn", tr("No code could be read in this photo"),
                                   tr("Put the boxes with the printed code facing up, use good light, and take the photo closer (about 30 to 90 cm above the boxes)."))
    else:
        parts = [count(known, "medicine") + tr(" recognised")] + ([count(unknown, "box", "boxes") + tr(" not recognised")] if unknown else []) \
            + ([count(missing, "box", "boxes") + tr(" with no code read")] if missing else [])
        light = tr(" On a white table, boxes without a code cannot be marked: check by eye that every box is in the list.") if boxes.light_table(image) else ""
        st.session_state.notice = ("ok" if not unknown and not missing else "warn", tr("Photo read"), esc(", ".join(parts)) + tr(". The list below shows them.") + light)


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
        return f'<div class="mt-pic none" title="{esc(tr("No picture"))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5M12 12v9"/></svg></div>'
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
        return tr("Go back to Medicines and add a photo that shows this box, or type the code printed on it.")
    if reason.startswith("the pack expired"):
        return tr("Do not use it. Ask a pharmacist for a new pack.")
    if reason.startswith("the pack is on several lines"):
        return tr("Go back to Doses and keep one line for this medicine.")
    if reason.startswith("several packs match"):
        return tr("Go back to Doses and write the name of the medicine the way it appears on the box.")
    if reason.startswith("the strength on the sheet does not match"):
        return tr("Compare the strength on the box with the doctor's paper and correct the line.")
    if reason.startswith("unrecognised dose"):
        return tr("Go back to Doses and choose the amount with the buttons.")
    return ""


def source_html(source: str) -> str:
    """A citation as small text, with the long URL turned into a link."""
    match = re.match(r"(.*?):?\s*(https?://\S+)$", source)
    return tr('{x0}. <a href="{x1}" target="_blank">Open the official page</a>', x0=esc(match.group(1)), x1=esc(match.group(2))) if match else esc(source)


def chip(text: str, kind: str = "grey") -> str:
    return f'<span class="mt-chip {kind}">{esc(text)}</span>'


def expiry_chip(expiry: date | None, today: date) -> str:
    if expiry is None:
        return chip(tr("Expiry date unknown"), "warn")
    if expiry < today:
        return chip(tr('Expired on {x0}', x0=expiry.isoformat()), "bad")
    if expiry <= today + timedelta(days=30):
        return chip(tr('Expires on {x0}', x0=expiry.isoformat()), "warn")
    return chip(tr('Expires on {x0}', x0=expiry.isoformat()), "grey")


MARK = "data:image/svg+xml;base64," + base64.b64encode((Path(__file__).resolve().parent.parent / "web" / "favicon.svg").read_bytes()).decode()


def brand_html() -> str:
    return f'<div class="mt-brandbar"><img src="{MARK}" alt=""><span><b>med-table</b><span>{esc(tr("Medication planner"))}</span></span></div>'


def steps_html(step: int) -> str:
    cells = "".join(f'<li class="mt-s {"cur" if i == step else "done" if i < step else ""}"{" aria-current=\"step\"" if i == step else ""}>'
                    f'<b>{"&#10003;" if i < step else i}</b><span>{esc(tr(name))}</span></li>' for i, name in enumerate(STEPS, 1))
    return f'<ol class="mt-steps">{cells}</ol>'


def notice() -> None:
    """One quiet line on every screen: a planning aid, not medical advice; on the public demo, the rest is folded under More."""
    helper = esc(tr("This is a helper for planning. It gives no medical advice and does not replace the doctor or the pharmacist."))
    if not public_demo():
        st.markdown(f'<div class="mt-note"><p style="padding:.5rem .8rem">{helper}</p></div>', unsafe_allow_html=True)
        return
    more = tr("Try it with the demo photo or the 3D room. Do not upload photos of real prescriptions or of anything showing a name, address or ID "
              "number: pictures are processed on a shared server (photos from the 3D room are deleted after an hour). This is a planning aid, not "
              "medical advice. In this online version the voice, reading the doctor's schedule with Muse Spark and SAM 3 are turned off; they run in "
              'the local installation (<a href="https://github.com/hsilvosa/med-table-meta-hackathon" target="_blank">source code</a>).')
    st.markdown(f'<details class="mt-note"><summary><b>{esc(tr("Public online demo"))}.</b> <span>{helper}</span><span class="mt-more">{esc(tr("More"))}</span></summary>'
                f'<p>{more}</p></details>', unsafe_allow_html=True)


def header(step: int, title: str, lead: str) -> None:
    st.markdown(f'<p class="mt-title">{esc(title)}</p><p class="mt-lead">{lead}</p>', unsafe_allow_html=True)


def nav(back: int | None, forward: int | None, forward_label: str = "", enabled: bool = True, why_not: str = "") -> None:
    left, right = st.columns(2) if forward else (st.container(), None)
    if back:
        left.button(tr("Back"), on_click=go, args=(back,), key=f"back{back}_{st.session_state.step}", width="stretch")
    if forward:
        right.button(forward_label, on_click=go, args=(forward,), type="primary", disabled=not enabled, key=f"next{forward}", width="stretch")
        if not enabled and why_not:
            right.markdown(f'<p class="mt-hint">{esc(why_not)}</p>', unsafe_allow_html=True)


@st.fragment(run_every="2s")
def watch_room() -> None:
    """Photos taken with the virtual phone in the 3D room load here by themselves."""
    if not latest_photo().exists() or latest_photo().stat().st_mtime <= st.session_state.room_seen:
        return
    st.session_state.room_seen = latest_photo().stat().st_mtime
    image = cv2.imread(str(latest_photo()))
    if image is not None:
        add_photo(f"{photo_source()}_{time.strftime('%H:%M:%S', time.localtime(latest_photo().stat().st_mtime))}", image)
        st.session_state.step = 1
        st.rerun()
