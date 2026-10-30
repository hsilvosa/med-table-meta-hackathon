"""Screens 3 and 4: check the plan, then print, listen and remind."""

import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from medtable import voice
from medtable.calendar_pdf import render_pdf
from medtable.pillbox_pdf import render_pillbox
from medtable.findings import NOT_A_FULL_CHECK
from medtable.pipeline import make_plan
from medtable.plan import NOT_CONFIRMED, SLOT_LABELS, box_days, large_amount, to_ics, units_in_pack
from medtable.schedule import SLOTS
from planner.common import ask_reset, box, esc, header, nav, page_preview, patient_field, saved_file, smpc_source, source_html, what_to_do
from planner.table import Table, changes, changes_box


def render(t: Table, step: int, use_smpc: bool) -> None:
    readings, rows, today = t.readings, t.rows, t.today
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
        changes_box(t, with_amounts=True)
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
                pdf_path = render_pdf(plan, Path(tmp) / "plan.pdf", st.session_state.patient, notes=st.session_state.plan_notes, times=times, changes=changes(t))
                pillbox_bytes = render_pillbox(plan, Path(tmp) / "pillbox.pdf", st.session_state.patient, times=times).read_bytes()
                pdf_bytes = pdf_path.read_bytes()
                preview = page_preview(pdf_path)
            if preview is not None:
                st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">This is the page you will print</p>', unsafe_allow_html=True)
                st.image(preview, width="stretch")
            st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A page to print</p><p class="mt-hint">Large print, with the official picture of each medicine.</p>', unsafe_allow_html=True)
            st.download_button("Download the calendar to print (PDF)", pdf_bytes, "medication_plan.pdf", "application/pdf", type="primary", width="stretch")
            st.markdown('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A guide to fill the weekly pill organiser</p>'
                        '<p class="mt-hint">One page: the seven days and four times of day, with what goes into each compartment.</p>', unsafe_allow_html=True)
            st.download_button("Download the pill organiser sheet (PDF)", pillbox_bytes, "pill_organiser.pdf", "application/pdf", width="stretch")
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
