"""Screens 3 and 4: check the plan, then print, listen and remind."""

import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from medtable import voice
from medtable.calendar_pdf import render_pdf
from medtable.findings import NOT_A_FULL_CHECK
from medtable.i18n import VOICE_CULTURE, language, tr, tr_reason
from medtable.pillbox_pdf import render_pillbox
from medtable.pipeline import make_plan
from medtable.plan import NOT_CONFIRMED, SLOT_LABELS, box_days, large_amount, to_ics, units_in_pack
from medtable.schedule import SLOTS
from planner.common import ask_reset, box, esc, header, nav, page_preview, patient_field, saved_file, smpc_source, source_html, what_to_do
from planner.table import Table, changes, changes_box


def render(t: Table, step: int, use_smpc: bool) -> None:
    readings, rows, today = t.readings, t.rows, t.today
    records = [r.as_record() for r in rows]
    with st.spinner(tr("Preparing the plan...")):
        result = make_plan(readings, st.session_state.manual, records, smpc_source() if use_smpc else None, today)
    plan = result.plan
    review = [f for f in plan.findings if f.kind != "unverified_item" and f.severity == "review"]
    info = [f for f in plan.findings if f.kind != "unverified_item" and f.severity == "info"]
    pending = [what for what, why in plan.not_included if why == NOT_CONFIRMED]      # waiting for the caregiver, not a problem yet
    left_out = [(what, why) for what, why in plan.not_included if why != NOT_CONFIRMED]
    doses = len(plan.entries)

    if step == 3:
        header(3, tr("Check the plan"), tr("This is exactly what will be printed. Read it through, and read what was left out and why."))
        if not doses:
            box("warn", tr("Nothing in the plan yet"),
                tr("Go back to <b>Doses</b>, choose the amounts and tick <b>Yes, this matches the doctor's schedule</b> for at least one medicine.")
                + (tr(' Waiting for you: {x0} medicine(s).', x0=len(pending)) if pending else ""))
        if st.session_state.patient:
            st.markdown(tr('<p class="mt-lead">Plan for <b>{x0}</b></p>', x0=esc(st.session_state.patient)), unsafe_allow_html=True)
        rows_html = []
        for slot in SLOTS:
            time_text = st.session_state.times[slot]
            items = "".join('<div style="margin-bottom:6px">' + tr("{dose} of {name}", dose=f'<span class="mt-dose">{esc(e.written())}</span>', name=esc(e.name))
                            + (f' <b>({esc(e.days_text())})</b>' if e.days_text() else '')
                            + (f' <span class="mt-meta">({esc(e.line.remarks)})</span>' if e.line.remarks else '') + '</div>' for e in plan.slot_entries(slot))
            rows_html.append(f'<tr><td class="mt-slot">{esc(tr(SLOT_LABELS[slot]))}<span class="mt-time">{esc(time_text)}</span></td>'
                             f'<td>{items or tr("<span class=mt-empty>Nothing</span>")}</td></tr>')
        with st.container(border=True):
            st.markdown(f'<table class="mt-agenda">{"".join(rows_html)}</table>', unsafe_allow_html=True)

        lines_in = {}
        for e in plan.entries:
            lines_in.setdefault(e.pack.medicine.cn, (e.pack.medicine, e.line))
        for medicine, line in lines_in.values():
            if (big := large_amount(line)):
                box("warn", tr('Please check the amount of {x0}', x0=medicine.name), tr("{big:g} a day is more than usual for one medicine. It is in the plan as you chose it: compare it with the doctor's paper.", big=big))
        lasting = []
        for medicine, line in lines_in.values():
            units = units_in_pack(medicine.presentation)
            if (days_left := box_days(units, line)):
                lasting.append(tr('<li><b>{x0}</b>: a full box of {units} lasts about <b>{days_left} days</b> at these amounts.</li>', x0=esc(medicine.name), units=units, days_left=days_left))
        if lasting:
            box("tip", tr("How long a box lasts"), tr('<ul style="margin:.3rem 0 0 1.1rem;padding:0">{x0}</ul><div class="mt-meta">Counted from the pack size listed by AEMPS CIMA, for a full box. Ask for the next box a week before.</div>', x0="".join(lasting)))
        changes_box(t, with_amounts=True)
        if pending and doses:
            box("tip", tr('Waiting for you ({x0})', x0=len(pending)), tr('Not in the plan until you tick the box on the Doses screen: {x0}.', x0=esc(', '.join(pending))))
        for what, why in left_out:
            if why == "could not be verified":      # here `what` is the reason the box was not recognised
                box("bad", tr("Left out: a box not recognised"), esc(tr_reason(what)[0].upper() + tr_reason(what)[1:]) + tr(". It is not in the plan."))
            else:
                box("bad", tr('Left out: {what}', what=what), esc(tr_reason(why)[0].upper() + tr_reason(why)[1:]) + "." + (tr(' <b>What to do:</b> {x0}', x0=esc(todo)) if (todo := what_to_do(why)) else ""))
        if review:
            st.markdown(tr('<p class="mt-title" style="font-size:1.3rem;margin-top:1rem">To ask your pharmacist ({x0})</p>', x0=len(review)), unsafe_allow_html=True)
            for f in review:
                quote = f'<div class="mt-quote">{esc(f.quote)}</div>' if f.quote else ""
                body = esc(f.text() if not f.quote else f.text().split(": " + chr(34))[0] + ".")
                box("warn", f.title, body + quote + (tr('<div class="mt-meta">Source: {x0}</div>', x0=source_html(f.source)) if f.source else ""))
        if info:
            with st.expander(tr('More information ({x0})', x0=len(info))):
                for f in info:
                    st.markdown(f"**{f.title}.** {f.text()}")
                    if f.source:
                        st.markdown(tr('<div class="mt-meta">Source: {x0}</div>', x0=source_html(f.source)), unsafe_allow_html=True)
        with st.expander(tr("What was checked, and what was not")):
            ran = (tr("Checks run: the same active ingredient in two boxes, the same drug group, the expiry date printed in the code, and whether each box matches the schedule")
                   + (tr(", and word-for-word quotes from sections 4.2 and 4.5 of the official leaflets (the quotes stay in Spanish, as AEMPS wrote them).") if plan.smpc_used
                      else tr(". The official leaflets were NOT consulted (turned off in Settings).")))
            if any(f.kind == "smpc_unavailable" for f in plan.findings):
                ran += tr(" For some medicine a leaflet section could not be checked (see the notes above).")
            st.write(f"{ran} {tr(NOT_A_FULL_CHECK)}")
        box("tip", tr("Remember"), tr("No warning does <b>not</b> mean the plan is safe. This helper schedules what the doctor prescribed; ask a pharmacist about the medicines together."))
        st.write("")
        nav(2, 4, tr("Next: print or listen"), enabled=bool(doses), why_not=tr("The plan is empty. Go back and choose doses."))

    else:
        header(4, tr("Print, listen, remind"), tr("Take the plan with you: a page for the fridge, a voice that reads it out, or reminders on a phone."))
        if not doses:
            box("warn", tr("Nothing to print yet"), tr("Go back and confirm at least one medicine."))
        with st.container(border=True):
            st.markdown(tr('<p class="mt-name">Before you print</p><p class="mt-hint">Both are optional. Anything left empty is printed as lines to write on by hand.</p>'), unsafe_allow_html=True)
            patient_field("patient_step4")
            st.text_area(tr("Notes for the whole plan (for example: doctor's phone number, allergies)"), value=st.session_state.plan_notes, key="plan_notes_box", height=110,
                         on_change=lambda: st.session_state.update(plan_notes=st.session_state.plan_notes_box.strip()))
            def set_time(slot: str) -> None:
                st.session_state.times[slot] = st.session_state[f"t_{slot}"].strftime("%H:%M")

            with st.expander(tr("Change the reminder times")):
                for s in SLOTS:
                    st.time_input(tr(SLOT_LABELS[s]), value=datetime.strptime(st.session_state.times[s], "%H:%M").time(), key=f"t_{s}", on_change=set_time, args=(s,))
            times = dict(st.session_state.times)
        if doses:
            with tempfile.TemporaryDirectory() as tmp:
                pdf_path = render_pdf(plan, Path(tmp) / "plan.pdf", st.session_state.patient, notes=st.session_state.plan_notes, times=times, changes=changes(t))
                pillbox_bytes = render_pillbox(plan, Path(tmp) / "pillbox.pdf", st.session_state.patient, times=times).read_bytes()
                pdf_bytes = pdf_path.read_bytes()
                preview = page_preview(pdf_path)
            if preview is not None:
                st.markdown(tr('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">This is the page you will print</p>'), unsafe_allow_html=True)
                st.image(preview, width="stretch")
            st.markdown(tr('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A page to print</p><p class="mt-hint">Large print, with the official picture of each medicine.</p>'), unsafe_allow_html=True)
            st.download_button(tr("Download the calendar to print (PDF)"), pdf_bytes, "medication_plan.pdf", "application/pdf", type="primary", width="stretch")
            st.markdown(tr('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">A guide to fill the weekly pill organiser</p>'
                        '<p class="mt-hint">One page: the seven days and four times of day, with what goes into each compartment.</p>'), unsafe_allow_html=True)
            st.download_button(tr("Download the pill organiser sheet (PDF)"), pillbox_bytes, "pill_organiser.pdf", "application/pdf", width="stretch")
            st.markdown(tr('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Listen to it</p><p class="mt-hint">A voice reads each time of day.</p>'), unsafe_allow_html=True)
            if voice.available(VOICE_CULTURE[language()]):
                if st.button(tr("Read the plan aloud"), width="stretch"):
                    with tempfile.TemporaryDirectory() as tmp:
                        st.session_state.voice = {slot: path.read_bytes() for slot, path in voice.render_voice(plan, Path(tmp), culture=VOICE_CULTURE[language()]).items()}
                for slot, audio in st.session_state.get("voice", {}).items():
                    st.markdown(f'<p class="mt-name" style="margin-top:.6rem">{esc(tr(SLOT_LABELS[slot]))}</p>', unsafe_allow_html=True)
                    st.audio(audio, format="audio/wav")
            else:
                st.caption(tr("Reading aloud needs a voice in this language on this computer; none is installed."))
            st.markdown(tr('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Reminders on a phone</p><p class="mt-hint">Open the file on the phone to add daily reminders to its calendar.</p>'), unsafe_allow_html=True)
            st.markdown(tr('<p class="mt-title" style="font-size:1.25rem;margin-top:1rem">Continue later</p><p class="mt-hint">'
                        'Saves the medicines and the doses (not the photos) in a small file. Open it next month on the first screen.</p>'), unsafe_allow_html=True)
            st.download_button(tr("Save this plan to continue later"), saved_file().encode("utf-8"), "medication_plan_saved.json", "application/json", width="stretch")
            st.download_button(tr("Download the phone reminders (.ics)"), to_ics(plan, times).encode("utf-8"), "medication_plan.ics", "text/calendar", width="stretch")
        st.write("")
        nav(3, None)
        st.button(tr("Start over with new medicines"), on_click=ask_reset, key="start_over_end", width="stretch")
