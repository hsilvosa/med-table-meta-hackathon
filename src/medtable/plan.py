"""From confirmed sheet lines and verified packs to a plan: what goes into the calendar, what does not, and why.

Nothing here invents a value. Doses and remarks are the caregiver's confirmed text; names, forms and sources come from
AEMPS CIMA through the pack's code. A line enters the plan only when the caregiver confirmed it, its pack is verified
and not expired, its strength agrees with the sheet and it is not ambiguous.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from .findings import Finding
from .rules import Pack
from .schedule import SLOTS, Line, Reconciliation, dose_number

NOT_CONFIRMED = "the caregiver has not confirmed this line"
SLOT_LABELS = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "bedtime": "Bedtime"}
DEFAULT_TIMES = {"breakfast": "08:30", "lunch": "14:00", "dinner": "21:00", "bedtime": "23:00"}
# CIMA writes the pharmaceutical form in Spanish; these keys are matched against it (accent-free, lower case)
FORM_NOUNS = (("comprimid", "tablet", "tablets"), ("capsula", "capsule", "capsules"), ("supositor", "suppository", "suppositories"),
              ("sobre", "sachet", "sachets"), ("granulado", "sachet", "sachets"), ("parche", "patch", "patches"))
SPOKEN = {2.0: "two", 3.0: "three", 4.0: "four", 5.0: "five", 6.0: "six"}
ABBREVIATIONS = ((r"\b(\d+)\s*h\b", r"\1 hours"), (r"\b(\d+)\s*min\b", r"\1 minutes"), (r"\b(\d+(?:[.,]\d+)?)\s*mg\b", r"\1 milligrams"),
                 (r"\b(\d+(?:[.,]\d+)?)\s*g\b", r"\1 grams"), (r"\bc/\b", "every"))


def form_noun(form: str | None) -> tuple[str, str]:
    """What one dose of this pharmaceutical form is called, singular and plural: ("tablet", "tablets"), or ("dose", "doses") when unknown."""
    text = "".join(c for c in (form or "").lower() if c.isalpha() or c == " ").replace("á", "a")
    for key, singular, plural in FORM_NOUNS:
        if key in text:
            return singular, plural
    return "dose", "doses"


@dataclass
class Entry:
    slot: str
    pack: Pack
    line: Line
    dose: str  # exactly as confirmed ("1", "1/2", "0,5")

    @property
    def name(self) -> str:
        return self.pack.medicine.name

    @property
    def noun(self) -> tuple[str, str]:
        return form_noun(self.pack.medicine.form)

    def written(self) -> str:
        """For print: the dose as confirmed, plus the unit noun, e.g. '1/2 tablet', '2 tablets'."""
        singular, plural = self.noun
        value = dose_number(self.dose)
        return f"{self.dose} {singular if value is not None and value <= 1 else plural}"

    def spoken(self) -> str:
        value = dose_number(self.dose)
        singular, plural = self.noun
        if value == 0.5:
            return f"half a {singular}"
        if value == 0.25:
            return f"a quarter of a {singular}"
        if value == 0.75:
            return f"three quarters of a {singular}"
        if value == 1:
            return f"one {singular}"
        if value == 1.5:
            return f"one and a half {plural}"
        return f"{SPOKEN.get(value) or self.dose.replace(',', ' point ')} {plural}"


@dataclass
class Plan:
    entries: list[Entry]
    not_included: list[tuple[str, str]]  # (what, why)
    findings: list[Finding]
    generated: date
    sources: list[str] = field(default_factory=list)
    smpc_used: bool = True  # False when the SmPC sections were not consulted at all

    def slot_entries(self, slot: str) -> list[Entry]:
        return [e for e in self.entries if e.slot == slot]


def build_plan(lines: list[Line], recon: Reconciliation, findings: list[Finding], today: date | None = None) -> Plan:
    today = today or date.today()
    entries: list[Entry] = []
    not_included: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if not line.confirmed:
            not_included.append((line.text, NOT_CONFIRMED))
        elif i in recon.blocked:
            not_included.append((line.text, recon.blocked[i]))
        elif i not in recon.matches:
            not_included.append((line.text, "no verified pack"))
        else:
            pack = recon.matches[i]
            if pack.expiry and pack.expiry < today:
                not_included.append((line.text, f"the pack expired on {pack.expiry.isoformat()}"))
                continue
            bad = [d for _, d in ((s, line.doses.get(s, "0")) for s in SLOTS) if dose_number(d) is None]
            if bad:
                not_included.append((line.text, f"unrecognised dose: {bad[0]}"))
                continue
            entries += [Entry(slot, pack, line, dose) for slot, dose in line.active_slots()]
    for f in findings:
        if f.kind == "unverified_item":
            not_included.append((f.detail or "unidentified pack", "could not be verified"))
    sources = sorted({e.pack.medicine.citation() for e in entries})
    return Plan(entries, not_included, findings, today, sources)


def speech_text(plan: Plan, slot: str) -> str:
    """What the voice says for one moment of the day, built only from confirmed fields."""
    entries = plan.slot_entries(slot)
    if not entries:
        return f"{SLOT_LABELS[slot]}: nothing in the plan."
    count = len(entries)
    parts = [f"{SLOT_LABELS[slot]}. There {'is' if count == 1 else 'are'} {count} medicine{'s' if count != 1 else ''}."]
    for e in entries:
        remark = e.line.remarks
        for pattern, repl in ABBREVIATIONS:
            remark = re.sub(pattern, repl, remark)
        parts.append(f"{e.spoken()} of {e.name}." + (f" {remark}." if remark else ""))
    return " ".join(parts)


def _ics_escape(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 content lines are at most 75 octets; continuation lines start with one space."""
    out, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > (75 if not out else 74):
            out.append(current)
            current, size = "", 0
        current += char
        size += width
    out.append(current)
    return "\r\n ".join(out)


def to_ics(plan: Plan, times: dict[str, str] | None = None, start: date | None = None, days: int | None = None) -> str:
    """Daily recurring reminders, one per moment of the day that has medication. `days=None` repeats until stopped."""
    times = {**DEFAULT_TIMES, **(times or {})}
    start = start or plan.generated
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//med-table//plan//EN", "CALSCALE:GREGORIAN"]
    for slot in SLOTS:
        entries = plan.slot_entries(slot)
        if not entries:
            continue
        hour, minute = times[slot].split(":")
        description = "\n".join(f"{e.written()} of {e.name}" + (f" ({e.line.remarks})" if e.line.remarks else "") for e in entries)
        description += "\nBased on the medication sheet confirmed by the caregiver. Ask a pharmacist if in doubt."
        rule = "RRULE:FREQ=DAILY" + (f";COUNT={days}" if days else "")
        lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@med-table", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start.strftime('%Y%m%d')}T{hour}{minute}00", "DURATION:PT15M", rule,
                  f"SUMMARY:{_ics_escape('Medication: ' + SLOT_LABELS[slot])}", f"DESCRIPTION:{_ics_escape(description)}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M", "DESCRIPTION:Time for the medication", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
