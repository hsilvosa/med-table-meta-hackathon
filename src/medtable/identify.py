"""From a photo to verified pack readings.

A reading is `verified` only when ALL of these hold: a Data Matrix was decoded, it parses as GS1, it yields a Codigo
Nacional whose check digit validates, and CIMA knows that CN. Everything else is `unverified` with the reasons, and
unverified items never reach the calendar. Expiry comes straight from the code, so an expired pack is flagged
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from . import cima, decode, gs1
from .resolve import Medicine, Resolver


UNREACHABLE = "the official database (AEMPS CIMA) could not be reached"


@dataclass
class Reading:
    status: str  # "verified" | "unverified"
    bbox: tuple[int, int, int, int]
    method: str
    raw: str
    cn: str | None = None
    medicine: Medicine | None = None
    expiry: date | None = None
    expired: bool | None = None
    lot: str | None = None
    serial: str | None = None
    problems: list[str] = field(default_factory=list)


def read_code(detection: decode.Detection, resolver: Resolver, today: date | None = None) -> Reading:
    reading = Reading("unverified", detection.bbox, detection.method, detection.text)
    try:
        code = gs1.parse_pack_code(detection.text)
    except ValueError as exc:
        reading.problems.append(f"not a GS1 element string: {exc}")
        return reading
    reading.expiry, reading.lot, reading.serial = code.expiry, code.lot, code.serial
    if code.expiry:
        reading.expired = code.expiry < (today or date.today())
    reading.cn = code.national.cn
    reading.problems += code.national.problems
    if not code.national.cn:
        return reading
    try:
        medicine = resolver.by_cn(code.national.cn)
    except cima.Unreachable:            # never verified by guess: the caregiver tries again when the connection is back
        reading.problems.append(UNREACHABLE)
        return reading
    if medicine is None:
        reading.problems.append(f"CIMA has no medicine with CN {code.national.cn[:6]}")
        return reading
    if medicine.presentation is None:
        reading.problems.append(f"CIMA does not list CN {code.national.cn[:6]} among the presentations of {medicine.name}")
        return reading
    reading.medicine, reading.status = medicine, "verified"
    return reading


def identify(img_bgr: np.ndarray, resolver: Resolver | None = None, today: date | None = None) -> list[Reading]:
    """Decode every Data Matrix in the photo and resolve each pack."""
    resolver = resolver or Resolver()
    return [read_code(d, resolver, today) for d in decode.find_datamatrix(img_bgr)]
