"""Screen 1: the medicines, from photos of the boxes, typed codes or a saved plan."""

import time
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from medtable import candidates, decode, identify, synthetic, vlm
from medtable.findings import explain_problem
from medtable.pipeline import manual_pack
from medtable.rules import Pack
from medtable.synthetic import DEMO_ITEMS
from planner.common import (
    add_photo,
    box,
    card,
    chip,
    dismiss_code,
    embedded,
    esc,
    expiry_chip,
    from_camera,
    header,
    latest_photo,
    nav,
    nocode_dealt_with,
    nocode_key,
    official_photo,
    open_saved,
    photo_source,
    remove_medicine,
    remove_photo,
    resolver,
    retry_lookups,
    undo_last,
)
from planner.table import Table, changes_box, medicine_card


def render(t: Table) -> None:
    entries, boxes_of, typed_only, unverified, medicines, today = t.entries, t.boxes_of, t.typed_only, t.unverified, t.medicines, t.today
    header(1, "Show me the medicines", "Take a photo of the medicine boxes on the table. I read the code printed on each box.")
    st.info("This is a helper for planning. It gives no medical advice and does not replace the doctor or the pharmacist.")
    if embedded():
        if from_camera():
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
            if latest_photo().exists() and c1.button(f"Load the latest {photo_source()} photo", width="stretch"):
                image = cv2.imread(str(latest_photo()))
                if image is None:
                    st.error(f"The latest {photo_source()} photo could not be opened.")
                else:
                    add_photo(f"{photo_source()}_{time.strftime('%H:%M:%S', time.localtime(latest_photo().stat().st_mtime))}", image)
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
    changes_box(t, with_amounts=False)
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
            medicine_card(t, rs[0].medicine, chips, rs)
            st.button("Remove this medicine", key=f"del_{cn}", on_click=remove_medicine, args=(cn, rs[0].medicine.name), type="tertiary")
    for pack in typed_only:
        with st.container(border=True):
            medicine_card(t, pack.medicine, chip("Added by you", "ok"), [])
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
                     + (('Bring the camera closer to this box, then press <b>Take photo</b>. ' if from_camera() else 'In the room, press <b>Close-up of the box with no code</b> on the left, then <b>Take photo</b>. ') if embedded() else "")
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
                        segments = candidates.segment(photo_path, folder)
                except Exception as exc:  # no GPU, SAM environment missing: typing the national code still works
                    st.error(f"This step could not run ({exc}). You can type the code on the box instead.")
                    continue
                factor = st.session_state.photo_scale.get(name, 1.0)
                codes = [decode.Detection(r.raw, tuple(int(v * factor) for v in r.bbox), r.method) for r in st.session_state.readings.get(name, [])]
                found += [(name, b) for b in candidates.boxes_without_code(segments, codes)]
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
