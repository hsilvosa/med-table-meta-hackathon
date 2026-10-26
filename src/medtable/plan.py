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

SLOT_LABELS = {"desayuno": "Desayuno", "comida": "Comida", "cena": "Cena", "acostarse": "Al acostarse"}
DEFAULT_TIMES = {"desayuno": "08:30", "comida": "14:00", "cena": "21:00", "acostarse": "23:00"}
FORM_NOUNS = (("comprimid", "comprimido", "comprimidos"), ("capsula", "cápsula", "cápsulas"), ("supositor", "supositorio", "supositorios"),
              ("sobre", "sobre", "sobres"), ("granulado", "sobre", "sobres"))
FEMININE = {"cápsula", "dosis"}
SPOKEN = {1.0: "un", 2.0: "dos", 3.0: "tres", 4.0: "cuatro", 0.5: "medio", 0.25: "un cuarto", 0.75: "tres cuartos", 1.5: "uno y medio"}
ABBREVIATIONS = ((r"\b(\d+)\s*h\b", r"\1 horas"), (r"\b(\d+)\s*min\b", r"\1 minutos"), (r"\b(\d+(?:[.,]\d+)?)\s*mg\b", r"\1 miligramos"),
                 (r"\b(\d+(?:[.,]\d+)?)\s*g\b", r"\1 gramos"), (r"\bc/\b", "cada"))


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
        form = (self.pack.medicine.form or "").lower()
        form = "".join(c for c in form if c.isalpha() or c == " ")
        for key, singular, plural in FORM_NOUNS:
            if key in form.replace("á", "a"):
                return singular, plural
        return "dosis", "dosis"

    def written(self) -> str:
        """For print: the dose as confirmed, plus the unit noun, e.g. '1/2 comprimido', '2 comprimidos'."""
        singular, plural = self.noun
        value = dose_number(self.dose)
        return f"{self.dose} {singular if value is not None and value <= 1 else plural}"

    def spoken(self) -> str:
        value = dose_number(self.dose)
        singular, plural = self.noun
        word = SPOKEN.get(value, self.dose.replace("/", " barra "))
        if singular in FEMININE:
            word = {"un": "una", "medio": "media", "uno y medio": "una y media"}.get(word, word)
        return f"{word} {singular if (value or 0) <= 1 or word == 'uno y medio' else plural}"


@dataclass
class Plan:
    entries: list[Entry]
    not_included: list[tuple[str, str]]  # (what, why)
    findings: list[Finding]
    generated: date
    sources: list[str] = field(default_factory=list)

    def slot_entries(self, slot: str) -> list[Entry]:
        return [e for e in self.entries if e.slot == slot]


def build_plan(lines: list[Line], recon: Reconciliation, findings: list[Finding], today: date | None = None) -> Plan:
    today = today or date.today()
    entries: list[Entry] = []
    not_included: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if not line.confirmed:
            not_included.append((line.text, "la línea no ha sido confirmada por el cuidador"))
        elif i in recon.blocked:
            not_included.append((line.text, recon.blocked[i]))
        elif i not in recon.matches:
            not_included.append((line.text, "sin envase verificado"))
        else:
            pack = recon.matches[i]
            if pack.expiry and pack.expiry < today:
                not_included.append((line.text, f"el envase caducó el {pack.expiry.isoformat()}"))
                continue
            bad = [d for _, d in ((s, line.doses.get(s, "0")) for s in SLOTS) if dose_number(d) is None]
            if bad:
                not_included.append((line.text, f"dosis no reconocida: {bad[0]}"))
                continue
            entries += [Entry(slot, pack, line, dose) for slot, dose in line.active_slots()]
    for f in findings:
        if f.kind == "unverified_item":
            not_included.append((f.detail or "envase sin identificar", "no se pudo verificar"))
    sources = sorted({e.pack.medicine.citation() for e in entries})
    return Plan(entries, not_included, findings, today, sources)


def speech_text(plan: Plan, slot: str) -> str:
    """What the voice says for one moment of the day, built only from confirmed fields."""
    entries = plan.slot_entries(slot)
    if not entries:
        return f"{SLOT_LABELS[slot]}: no hay medicación en el plan."
    parts = [f"{SLOT_LABELS[slot]}. Hay {len(entries)} medicamento{'s' if len(entries) != 1 else ''}."]
    for e in entries:
        remark = e.line.remarks
        for pattern, repl in ABBREVIATIONS:
            remark = re.sub(pattern, repl, remark)
        parts.append(f"{e.spoken()} de {e.name}." + (f" {remark}." if remark else ""))
    return " ".join(parts)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(plan: Plan, times: dict[str, str] | None = None, start: date | None = None, days: int | None = None) -> str:
    """Daily recurring reminders, one per moment of the day that has medication. `days=None` repeats until stopped."""
    times = {**DEFAULT_TIMES, **(times or {})}
    start = start or plan.generated
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//med-table//plan//ES", "CALSCALE:GREGORIAN"]
    for slot in SLOTS:
        entries = plan.slot_entries(slot)
        if not entries:
            continue
        hour, minute = times[slot].split(":")
        description = "\n".join(f"{e.written()} de {e.name}" + (f" ({e.line.remarks})" if e.line.remarks else "") for e in entries)
        description += "\nSegún la hoja de medicación confirmada. Consulte a su farmacéutico ante cualquier duda."
        rule = "RRULE:FREQ=DAILY" + (f";COUNT={days}" if days else "")
        lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@med-table", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start.strftime('%Y%m%d')}T{hour}{minute}00", "DURATION:PT15M", rule,
                  f"SUMMARY:{_ics_escape('Medicación: ' + SLOT_LABELS[slot])}", f"DESCRIPTION:{_ics_escape(description)}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M", "DESCRIPTION:Hora de la medicación", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
