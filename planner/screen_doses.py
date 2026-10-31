"""Screen 2: the doses, chosen by the caregiver and confirmed medicine by medicine."""

import tempfile
from pathlib import Path

import streamlit as st

from medtable import sheet_reader, vlm
from medtable.form import CHOICE_LABELS, CHOICE_VALUES, OTHER, QUICK_NOTES, Row, choice_for, merge_read_rows
from medtable.i18n import tr
from medtable.plan import DAY_SHORT, SLOT_LABELS, form_noun, large_amount
from medtable.rules import Pack
from medtable.schedule import ALL_DAYS, SLOTS, dose_number
from planner.common import public_demo, SLOT_HINT, card, chip, count, days_words, dose_words, esc, header, latest_photo, line_of, nav, official_photo, patient_field, photo_source, unconfirm
from planner.table import Table


def render(t: Table) -> None:
    rows, medicines, expired_cns = t.rows, t.medicines, t.expired_cns
    header(2, tr("Choose the doses"),
           tr("For each medicine, choose <b>how many to take</b> at each time of day, as written on the doctor's paper. "
           "Then tick the box under it. No amount is filled in for you, and medicines that are not ticked stay out of the plan."))
    ready = sum(1 for r in rows if r.confirmed and r.has_dose)
    if rows:
        st.progress(ready / len(rows), text=tr('{ready} of {x1} ready for the plan', ready=ready, x1=count(len(rows), 'medicine')))
    patient_field("patient_step2")
    if not public_demo():      # the model call sends a picture to the Meta Model API: not offered on the shared server
        with st.expander(tr("Have a photo of the doctor's schedule? Let the computer copy it (optional)")):
            backend = vlm.backend_name()
            if backend == "meta":
                st.warning(tr("The photo LEAVES this computer and goes to the Meta API. Use it only for a sheet without personal data "
                           "(no name, ID number or address). To keep it on this computer, whoever installed the tool can switch it to the offline model (VLM_BACKEND=local)."))
            else:
                st.caption(tr("Local model: the picture does not leave this computer."))
            sheet_photo = st.file_uploader(tr("Photo of the schedule"), type=["jpg", "jpeg", "png"], key="sheet_photo")
            consent = st.checkbox(tr("I understand where the picture is sent and want the computer to read it"), key="sheet_consent") if backend == "meta" else True
            sources = []
            if sheet_photo:
                sources.append((tr("Read the schedule"), sheet_photo.name, sheet_photo.getvalue()))
            if latest_photo().exists():
                sources.append((tr('Read the latest {x0} photo as the schedule', x0=tr(photo_source())), f"{photo_source()}_schedule.jpg", latest_photo().read_bytes() if consent else b""))
            for label, file_name, content in sources:
                if st.button(label, disabled=not consent, width="stretch", key=f"read_{file_name}"):
                    with tempfile.TemporaryDirectory() as tmp:
                        path = Path(tmp) / file_name
                        path.write_bytes(content)
                        try:
                            with st.spinner(tr("Reading the schedule...")):
                                read = sheet_reader.read_sheet(path, consent=consent is True)
                        except Exception as exc:  # network, budget cap, server not running: tell the caregiver, keep manual entry available
                            st.error(tr('The schedule could not be read ({exc}). You can choose the doses by hand below.', exc=exc))
                        else:
                            packs_now = [Pack(m, "verified") for m in medicines]
                            changed, merge_notes = merge_read_rows(rows, read.rows, packs_now)      # bumps `rev`, so the buttons show what was read
                            st.session_state.sheet_notes = read.problems + merge_notes + [tr("Check every medicine against the paper: a computer reading can contain mistakes.")]
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
                body += chip(tr("Box on the table"), "ok")
            else:
                body += chip(tr("No matching box in the photos"), "warn")
            if row.cn in expired_cns:
                body += tr('<div class="mt-alert">The box has expired: this medicine will be left out of the plan until there is a new box.</div>')
            if row.sheet_name and row.sheet_name != row.medicine:
                body += tr('<div class="mt-meta">The schedule says: {x0}</div>', x0=esc(row.sheet_name))
            form = pack.form if pack else None
            if (big := large_amount(line_of(row))):
                body += tr('<div class="mt-alert">Please check: {big:g} a day is more than usual for one medicine. Compare it with the doctor\'s paper.</div>', big=big)
            if row.confirmed and row.has_dose:          # done: a short summary instead of 28 buttons, so the list stays short
                taken = [f"{esc(tr(SLOT_LABELS[s]))}: <b>{esc(dose_words(row.doses[s], form))}</b>" for s in SLOTS if dose_number(row.doses[s]) != 0]
                if (when := days_words(row.days)):
                    taken.append(f"<b>{esc(when)}</b>")
                body += chip(tr("Ready for the plan"), "ok") + f'<div class="mt-sum">{" &middot; ".join(taken)}</div>' \
                    + (tr('<div class="mt-meta">Note: {x0}</div>', x0=esc(row.note)) if row.note else "")
                card(official_photo(pack) if pack else None, body, plain=True)
                st.button(tr("Change the amounts"), key=f"edit_{row.id}", on_click=unconfirm, args=(row,))
                continue
            card(official_photo(pack) if pack else None, body, plain=True)
            plural = form_noun(form)[1]
            for slot in SLOTS:
                question = tr('how many {plural}?', plural=tr(plural)) if plural != "doses" else tr("how many?")
                st.segmented_control(f"{tr(SLOT_LABELS[slot])} ({tr(SLOT_HINT[slot])}): {question}", CHOICE_VALUES + [OTHER], format_func=lambda v: tr(CHOICE_LABELS[v]),
                                     default=choice_for(row.doses[slot]), key=row.key("dose", slot), on_change=set_dose, args=(row, slot))
                if choice_for(row.doses[slot]) == OTHER:
                    st.text_input(tr("Type the amount (for example 4 or 2,5)"), value=row.doses[slot], key=row.key("other", slot), on_change=set_other, args=(row, slot))
            every = tuple(row.days) == ALL_DAYS
            st.segmented_control(tr("Which days?"), ["every", "some"], format_func={"every": tr("Every day"), "some": tr("Only some days of the week")}.get,
                                 default="every" if every else "some", key=row.key("often"), on_change=set_often, args=(row,))
            if not every:
                st.pills(tr("Tick the days it is taken"), list(range(7)), format_func=lambda d: tr(DAY_SHORT[d]), selection_mode="multi", default=list(row.days),
                         key=row.key("days"), on_change=set_days, args=(row,))
                if not row.days:
                    st.markdown(tr('<p class="mt-hint">Tick at least one day.</p>'), unsafe_allow_html=True)
            with st.expander(tr("Add a note to print next to this medicine (optional)"), expanded=bool(row.note)):
                st.pills(tr("Tick what the doctor's paper says"), QUICK_NOTES, format_func=tr, selection_mode="multi", default=row.quick, key=row.key("quick"), on_change=set_quick, args=(row,))
                st.text_input(tr("Anything else (for example: white tablet, keep in the fridge)"), value=row.remarks, key=row.key("remarks"), on_change=set_field,
                              args=(row, "remarks", row.key("remarks")))
            st.checkbox(tr("Yes, this matches the doctor's schedule"), value=row.confirmed, key=row.key("ok"), on_change=set_field, args=(row, "confirmed", row.key("ok")))
            if row.confirmed and row.has_dose:
                st.markdown(chip(tr("Will be in the plan"), "ok"), unsafe_allow_html=True)
            elif row.confirmed:
                st.markdown(chip(tr("Ticked, but every amount is None"), "warn"), unsafe_allow_html=True)
            else:
                st.markdown(chip(tr("Not in the plan yet: choose the amounts, then tick the box"), "grey"), unsafe_allow_html=True)

    with st.expander(tr("A medicine on the schedule that has no box on the table")):
        st.write(tr("Type its name as written on the schedule. The plan will list it as \"on the schedule but not on the table\"."))
        def add_line() -> None:      # a callback: a widget's value can only be changed before the widget is created in a run
            name = st.session_state.extra_name.strip()
            if name:
                st.session_state.rows.append(Row(f"hand{len(st.session_state.rows) + 1}", name))
                st.session_state.extra_name = ""

        extra = st.text_input(tr("Name on the schedule"), key="extra_name")
        st.button(tr("Add this line"), on_click=add_line, disabled=not extra.strip(), width="stretch")
    st.write("")
    nav(1, 3, tr("Next: see the plan"), enabled=bool(rows), why_not=tr("There are no medicines yet. Go back and add one."))
    st.caption(tr('{ready} of {x1} will be in the plan.', ready=ready, x1=count(len(rows), 'medicine')))
