"""The caregiver's sheet as a list of rows, one per medicine, with big-button dose choices.

A row is one line of the doctor's schedule. Rows for verified packs start with every dose at "None" and unconfirmed: the tool never
proposes an amount. Rows read from a photo of the sheet are merged into the row of the pack they name (when that is unambiguous and
the row is still untouched); anything else becomes its own row, and the plan then reports it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rules import Pack
from .schedule import SLOTS, Line, dose_number, lines_from_rows, reconcile

# (value stored on the sheet, label on the button). Anything else is typed in by the caregiver under "Other".
DOSE_CHOICES = (("0", "None"), ("1/4", "\u00bc"), ("1/2", "\u00bd"), ("1", "1"), ("1,5", "1\u00bd"), ("2", "2"), ("3", "3"))
OTHER = "other"
CHOICE_VALUES = [value for value, _ in DOSE_CHOICES]
CHOICE_LABELS = {**dict(DOSE_CHOICES), OTHER: "Other"}


def choice_for(dose: str) -> str:
    """The button that shows this dose: itself when it is one of the buttons, else 'Other'."""
    return dose if dose in CHOICE_VALUES else OTHER


@dataclass
class Row:
    id: str
    medicine: str  # as on the sheet, or the pack's name for rows created from a pack
    cn: str | None = None  # the pack this row is tied to (rows created from a verified pack)
    doses: dict[str, str] = field(default_factory=lambda: dict.fromkeys(SLOTS, "0"))
    remarks: str = ""
    confirmed: bool = False
    sheet_name: str = ""  # how the reader saw the medicine, when it differs from the pack name

    @property
    def untouched(self) -> bool:
        return not self.confirmed and not self.remarks and all(d == "0" for d in self.doses.values())

    @property
    def has_dose(self) -> bool:
        return any(dose_number(d) != 0 for d in self.doses.values())

    def as_record(self) -> dict:
        return {"medicine": self.medicine, **self.doses, "remarks": self.remarks, "confirmed": self.confirmed, "cn": self.cn}


def row_for_pack(medicine) -> Row:
    return Row(f"pack{medicine.cn}", medicine.name, medicine.cn)


def sync_pack_rows(rows: list[Row], medicines) -> list[Row]:
    """Add one empty row per verified pack that has no row yet."""
    known = {r.cn for r in rows if r.cn}
    added = []
    for m in medicines:
        if m.cn not in known:
            known.add(m.cn)
            added.append(row_for_pack(m))
    rows.extend(added)
    return added


def merge_read_rows(rows: list[Row], read: list[dict], packs: list[Pack]) -> tuple[list[Row], list[str]]:
    """Put the rows read from a photo of the sheet into `rows`. Returns the rows that changed and notes for the caregiver.

    A read row goes into the existing row of a pack only when it names exactly one pack and that row is still untouched;
    otherwise it is added as its own row (and the plan will say if two rows end up on one pack). Nothing is ever confirmed.
    """
    changed, notes = [], []
    for item in read:
        line = lines_from_rows([item])[0][0]
        recon = reconcile([line], packs)
        pack = recon.matches.get(0) if 0 not in recon.blocked else None
        target = next((r for r in rows if pack and r.cn == pack.medicine.cn and r.untouched), None)
        doses = {s: str(item.get(s, "") or "0").strip() for s in SLOTS}
        if target:
            target.doses, target.remarks, target.sheet_name = doses, str(item.get("remarks", "") or "").strip(), line.text
            changed.append(target)
            continue
        if any(r.medicine == line.text for r in rows):
            notes.append(f'"{line.text}" is already in the list, so the new line was not added. Check the list in case they were different lines.')
            continue
        row = Row(f"sheet{len(rows) + 1}", line.text, None, doses, str(item.get("remarks", "") or "").strip())
        rows.append(row)
        changed.append(row)
    return changed, notes
