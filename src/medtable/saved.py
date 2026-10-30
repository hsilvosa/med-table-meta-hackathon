"""Save a plan to a small file and open it again later (a caregiver updates the plan every month).

The file holds what the caregiver decided and the code texts that were read, never the photos. Opening it reads every code again
against AEMPS CIMA, as on the first day: a pack is verified only by its code, never because a file says so, and an expiry date that
has passed since is caught again.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date

from .form import Row

VERSION = 1


def dump(*, rows: list[Row], codes: list[str], typed_cns: list[str], patient: str, notes: str, times: dict[str, str],
         removed_cns: set[str], removed_raw: set[str], today: date | None = None) -> str:
    return json.dumps({
        "app": "med-table", "version": VERSION, "saved": (today or date.today()).isoformat(),
        "patient": patient, "notes": notes, "times": times,
        "codes": codes, "typed_cns": typed_cns, "removed_cns": sorted(removed_cns), "removed_raw": sorted(removed_raw),
        "rows": [asdict(r) for r in rows],
    }, ensure_ascii=False, indent=1)


def load(text: str) -> dict:
    """The saved values, checked: raises ValueError with a plain sentence when the file is not a saved plan."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("This file is not a saved plan (it could not be read).") from None
    if not isinstance(data, dict) or data.get("app") != "med-table":
        raise ValueError("This file is not a plan saved by this tool.")
    if data.get("version") != VERSION:
        raise ValueError("This plan was saved by another version of the tool and cannot be opened here.")
    known = {f.name for f in fields(Row)}
    try:
        rows = [Row(**{k: v for k, v in r.items() if k in known}) for r in data.get("rows", [])]
    except TypeError:
        raise ValueError("This saved plan is damaged (a line could not be read).") from None
    for r in rows:
        r.rev += 1          # new widget keys, so the buttons show the opened values
    return {"rows": rows, "codes": [str(c) for c in data.get("codes", [])], "typed_cns": [str(c) for c in data.get("typed_cns", [])],
            "patient": str(data.get("patient", "")), "notes": str(data.get("notes", "")), "times": dict(data.get("times") or {}),
            "removed_cns": set(data.get("removed_cns", [])), "removed_raw": set(data.get("removed_raw", [])), "saved": str(data.get("saved", ""))}
