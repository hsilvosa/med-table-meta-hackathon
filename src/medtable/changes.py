"""What changed since a saved plan: new medicines, medicines not seen again, and amounts or days that are different.

Used when a plan saved last month is opened and new photos are taken. It compares the caregiver's own rows (saved and current) and
the boxes read in the new photos; it decides nothing: every difference is shown so the caregiver can check it against the doctor's paper.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .form import CHOICE_LABELS, Row
from .i18n import tr
from .plan import DAY_SHORT, SLOT_LABELS
from .schedule import ALL_DAYS, SLOTS


@dataclass
class Changes:
    new: list[str] = field(default_factory=list)              # in the list now, not in the saved plan
    not_seen: list[str] = field(default_factory=list)         # in the saved plan, not in any photo taken since it was opened
    amounts: list[tuple[str, list[str]]] = field(default_factory=list)   # (medicine, ["Breakfast: 1 -> 1/2", ...])

    def __bool__(self) -> bool:
        return bool(self.new or self.not_seen or self.amounts)


def _days(days) -> str:
    return tr("every day") if tuple(days) == ALL_DAYS else (", ".join(tr(DAY_SHORT[d]) for d in days) or tr("no day"))


def _dose(dose: str) -> str:
    return tr(CHOICE_LABELS.get(dose, dose or "?"))


def _key(row: Row) -> str:
    return row.cn or row.medicine.strip().lower()


def compare(saved_rows: list[Row], rows: list[Row], seen_cns: set[str] | None = None) -> Changes:
    """`seen_cns`: national codes read in the photos taken after the plan was opened; None when there is no new photo yet
    (then nothing is reported as not seen: there is nothing to compare with)."""
    before = {_key(r): r for r in saved_rows}
    now = {_key(r): r for r in rows}
    changes = Changes(new=[r.medicine for k, r in now.items() if k not in before])
    if seen_cns is not None:
        changes.not_seen = [r.medicine for r in saved_rows if r.cn and r.cn not in seen_cns]
    for key, old in before.items():
        if key not in now:
            continue
        new = now[key]
        diff = [f"{tr(SLOT_LABELS[s])}: {_dose(old.doses.get(s, '0'))} -> {_dose(new.doses.get(s, '0'))}" for s in SLOTS if old.doses.get(s, "0") != new.doses.get(s, "0")]
        if list(old.days) != list(new.days):
            diff.append(tr('Days: {x0} -> {x1}', x0=_days(old.days), x1=_days(new.days)))
        if diff:
            changes.amounts.append((new.medicine, diff))
    return changes
