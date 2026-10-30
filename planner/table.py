"""What is on the table: the boxes read in the photos and the typed codes, grouped by medicine, and the caregiver's rows."""

from dataclasses import dataclass, field
from datetime import date

import streamlit as st

from medtable.changes import Changes, compare
from medtable.form import Row, sync_pack_rows
from medtable.i18n import tr
from planner.common import box, card, esc, official_photo


@dataclass
class Table:
    today: date
    entries: list = field(default_factory=list)        # (photo name, reading), one per physical pack, without what the caregiver removed
    boxes_of: dict = field(default_factory=dict)       # national code -> the readings of every box of that medicine
    typed_only: list = field(default_factory=list)     # typed or confirmed packs with no box read in a photo
    medicines: list = field(default_factory=list)
    expired_cns: set = field(default_factory=set)
    rows: list[Row] = field(default_factory=list)

    @property
    def readings(self) -> list:
        return [r for _, r in self.entries]

    @property
    def unverified(self) -> list:
        return [(n, r) for n, r in self.entries if r.status != "verified" or not r.medicine]


def current(today: date) -> Table:
    """Computed on every run from the session state (cheap: the lookups are cached). Also keeps one dose row per medicine."""
    t, seen = Table(today), set()
    for name, rs in st.session_state.readings.items():
        for r in rs:          # the same code text twice is the same pack seen in two photos
            removed = (r.medicine.cn in st.session_state.removed_cns) if r.medicine else (r.raw in st.session_state.removed_raw)
            if r.raw not in seen and not removed:
                seen.add(r.raw)
                t.entries.append((name, r))
    for r in t.readings:
        if r.status == "verified" and r.medicine:     # two boxes of one medicine are one medicine
            t.boxes_of.setdefault(r.medicine.cn, []).append(r)
    t.typed_only = [p for p in st.session_state.manual if p.medicine.cn not in t.boxes_of]
    t.medicines = [rs[0].medicine for rs in t.boxes_of.values()] + [p.medicine for p in t.typed_only]
    t.expired_cns = {cn for cn, rs in t.boxes_of.items() if all(r.expiry and r.expiry < today for r in rs)}
    sync_pack_rows(st.session_state.rows, t.medicines)
    t.rows = st.session_state.rows
    return t


def changes(t: Table) -> Changes | None:
    """What changed since the saved plan that was opened; None when no saved plan was opened."""
    baseline = st.session_state.get("baseline")
    if not baseline:
        return None
    new_photos = [n for n in st.session_state.readings if n != "saved plan"]
    seen = {r.medicine.cn for n in new_photos for r in st.session_state.readings[n] if r.medicine} if new_photos else None
    return compare(baseline["rows"], t.rows, seen)


def changes_box(t: Table, with_amounts: bool) -> None:
    found = changes(t)
    if not found or not (found.new or found.not_seen or (with_amounts and found.amounts)):
        return
    items = [tr('<li><b>New:</b> {x0}</li>', x0=esc(name)) for name in found.new]
    items += [tr('<li><b>Not seen in the new photos:</b> {x0}. Is it still taken? If not, remove it.</li>', x0=esc(name)) for name in found.not_seen]
    if with_amounts:
        items += [f"<li><b>{esc(name)}:</b> {esc('; '.join(diff))}</li>" for name, diff in found.amounts]
    box("warn", tr('What changed since the plan saved on {x0}', x0=st.session_state.baseline['saved']),
        tr('<ul style="margin:.3rem 0 0 1.1rem;padding:0">{x0}</ul><div class="mt-meta">Check each change against the doctor\'s paper.</div>', x0="".join(items)))


def shared_ingredient(t: Table, medicine) -> list[str]:
    """The other medicines in the list with an active ingredient in common (a fact from CIMA, shown so the caregiver can ask)."""
    mine = {a.strip().lower() for a in medicine.active_ingredients}
    return [m.name for m in t.medicines if m.cn != medicine.cn and mine & {a.strip().lower() for a in m.active_ingredients}]


def medicine_card(t: Table, medicine, chips: str, rs: list) -> None:
    body = f'<div class="mt-name">{esc(medicine.name)}</div>' + chips
    if medicine.active_ingredients:
        body += tr('<div class="mt-meta">Active ingredient: {x0}</div>', x0=esc(", ".join(a.capitalize() for a in medicine.active_ingredients)))
    old = [r for r in rs if r.expiry and r.expiry < t.today]
    if old and len(old) == len(rs):
        body += tr('<div class="mt-alert">This box has expired. Do not use it: it will be left out of the plan.</div>')
    elif old:
        body += tr('<div class="mt-alert">{x0} of {x1} boxes have expired. Do not use the expired one.</div>', x0=len(old), x1=len(rs))
    if (others := shared_ingredient(t, medicine)):
        body += tr('<div class="mt-heads">Same active ingredient as: {x0}. The plan lists it for the pharmacist.</div>', x0=esc("; ".join(others)))
    card(official_photo(medicine), body, plain=True)
