"""Read a photographed medication sheet into editable rows with a vision-language model.

The model only transcribes: cells are copied as written, nothing is interpreted or completed, and every row comes back
unconfirmed so the caregiver checks it. A cell that is not a recognised dose is kept as read (never replaced by "0");
the plan then refuses that line until the caregiver corrects it.

Privacy: with the `meta` backend the image leaves this machine. Use it only with sheets without personal data; the
`local` backend (Qwen through llama-server) keeps everything on the machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import vlm
from .schedule import SLOTS, dose_number

SHEET_PROMPT = ('This is a photo of a medication plan sheet written in Spanish. Extract ALL rows of the table as JSON: '
                '[{"medicine": str, "breakfast": str, "lunch": str, "dinner": str, "bedtime": str, "remarks": str}]. '
                'The dose columns are Desayuno (breakfast), Comida (lunch), Cena (dinner) and Acostarse (bedtime). '
                'Copy the values exactly as written (for example "1", "0", "1/2"); keep the medicine name and the remarks as written, in Spanish. '
                'If a cell is empty use "". Do not interpret, complete or correct anything.')
FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4"}


@dataclass
class SheetReading:
    rows: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # shown to the caregiver
    backend: str = ""
    cost_usd: float = 0.0


def clean_dose(value: object) -> str:
    """Typographic clean-up only: unicode fractions and stray spaces. Anything else is left as read."""
    text = str(value if value is not None else "").strip()
    for symbol, plain in FRACTIONS.items():
        text = re.sub(rf"(?<!\d){symbol}", plain, text)  # only a standalone fraction; "1½" stays as read and is rejected
    return re.sub(r"\s*/\s*", "/", text)


def rows_from_reply(text: str) -> SheetReading:
    data = vlm.parse_json(text)
    reading = SheetReading()
    if isinstance(data, dict):  # some models wrap the list: {"filas": [...]}
        data = next((v for v in data.values() if isinstance(v, list)), None)
    if not isinstance(data, list) or not data:
        reading.problems.append("No se pudo leer ninguna fila de la hoja. Escriba la pauta a mano.")
        return reading
    for number, raw in enumerate(data, 1):
        if not isinstance(raw, dict) or not str(raw.get("medicine", "")).strip():
            reading.problems.append(f"Row {number}: no medicine name; skipped.")
            continue
        row = {"medicine": str(raw["medicine"]).strip(), "remarks": str(raw.get("remarks") or "").strip(),
               "confirmed": False, "cn": None}
        empty = []
        for slot in SLOTS:
            cell = clean_dose(raw.get(slot))
            if cell and dose_number(cell) is None:
                reading.problems.append(f"Row {number} ({row['medicine']}), {slot}: \"{cell}\" is not a recognised dose; correct it.")
            if not cell:
                empty.append(slot)
            row[slot] = cell or "0"
        if empty:
            reading.problems.append(f"Row {number} ({row['medicine']}): empty or unread cell in {', '.join(empty)}; set to 0. Check it on the sheet.")
        reading.rows.append(row)
    return reading


def read_sheet(image: Path | str, backend: str | None = None) -> SheetReading:
    reply = vlm.ask_image(image, SHEET_PROMPT, backend=backend, max_tokens=2500, note="sheet reader")
    reading = rows_from_reply(reply.text)
    reading.backend = vlm.backend_name(backend)
    reading.cost_usd = reply.cost_usd
    return reading
