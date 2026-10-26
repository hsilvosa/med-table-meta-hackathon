"""Codigo Nacional (CN) helpers.

A Spanish pack carries a 7-digit CN: six digits plus a check digit. The check digit equals the GS1 EAN-13 check
digit of the GTIN `847000` + CN6 (hypothesis verified so far on printed CN reads only; to be confirmed on real packs).
"""

from __future__ import annotations

import re

GTIN_PREFIX = "847000"


def check_digit(cn6: str) -> int:
    """EAN-13 check digit of 847000 + the six CN digits."""
    if not re.fullmatch(r"\d{6}", cn6):
        raise ValueError(f"CN needs exactly 6 digits, got {cn6!r}")
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(GTIN_PREFIX + cn6))
    return (10 - total % 10) % 10


def is_valid(cn: str) -> bool:
    """True for a 7-digit CN (separators allowed) whose last digit matches the check digit."""
    digits = re.sub(r"\D", "", cn)
    return len(digits) == 7 and check_digit(digits[:6]) == int(digits[6])


def find_cn(text: str) -> str | None:
    """First 6+1 digit group in free text, e.g. '725702.8' or '7257028', as 7 digits; None when absent."""
    match = re.search(r"(?<!\d)(\d{6})[.\s-]?(\d)(?!\d)", text or "")
    return match.group(1) + match.group(2) if match else None


def gtin13(cn6: str) -> str:
    return GTIN_PREFIX + cn6 + str(check_digit(cn6))
