"""GS1 element strings as printed in the Data Matrix of Spanish medicine packs.

A pack carries a GS1 Data Matrix with the product code, expiry, batch and serial number:

  (01) GTIN, 14 digits       NTIN form "0" + 847000 + CN6 + check digit, or a regular GTIN
  (17) expiry YYMMDD         day 00 means "last day of the month"
  (10) batch / lot           variable length
  (21) serial number         variable length
  (712) Spanish national code (7 digits, CN6 + check digit); required when (01) is a regular GTIN

Sources: AEMPS note on the national code and safety features; GS1 General Specifications for the AI table.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date

from . import cn as cn_module

GS = "\x1d"  # group separator that ends a variable-length field
FIXED_LENGTH = {"00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2}
VARIABLE_MAX = {"10": 20, "21": 20, "240": 30, "241": 30, "710": 20, "711": 20, "712": 20, "713": 20, "714": 20, "715": 20}
SPAIN_PREFIX = "847000"


def _normalise(text: str) -> str:
    text = re.sub(r"^\](?:d2|C1|e0|Q3)", "", text.strip())  # symbology identifier
    return text.replace("<GS>", GS).replace("\\x1d", GS).replace("\\u001d", GS)


def parse_elements(text: str) -> dict[str, str]:
    """Split a GS1 element string into {AI: value}. Accepts the human-readable form "(01)...(17)..." and the raw form."""
    text = _normalise(text)
    if "(" in text:
        return {ai: value.replace(GS, "") for ai, value in re.findall(r"\((\d{2,4})\)([^(]*)", text)}
    fields: dict[str, str] = {}
    pos = 0
    while pos < len(text):
        if text[pos] == GS:
            pos += 1
            continue
        for size in (2, 3, 4):
            ai = text[pos:pos + size]
            if ai in FIXED_LENGTH:
                length = FIXED_LENGTH[ai]
                break
            if ai in VARIABLE_MAX:
                length = None
                break
        else:
            raise ValueError(f"unknown application identifier at position {pos}: {text[pos:pos + 6]!r}")
        pos += size
        if length is not None:
            value = text[pos:pos + length]
            if len(value) != length:
                raise ValueError(f"AI {ai} needs {length} characters, got {len(value)}")
        else:
            end = text.find(GS, pos)
            end = len(text) if end < 0 else end
            value = text[pos:min(end, pos + VARIABLE_MAX[ai])]
            length = len(value)
        fields[ai] = value
        pos += length
    return fields


def parse_expiry(yymmdd: str) -> date:
    """GS1 date; day 00 is the last day of the month. Years are read as 2000-2099."""
    year, month, day = 2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    if day == 0:
        day = calendar.monthrange(year, month)[1]
    return date(year, month, day)


@dataclass
class NationalCode:
    cn: str | None  # 7 digits with check digit, only when it validates
    source: str | None  # "ntin" (from AI 01) or "ai712"
    problems: list[str] = field(default_factory=list)


@dataclass
class PackCode:
    gtin: str | None
    expiry: date | None
    lot: str | None
    serial: str | None
    national: NationalCode
    fields: dict[str, str]


def national_code(fields: dict[str, str]) -> NationalCode:
    """Derive the Codigo Nacional from the NTIN in (01) or from (712); never returns an unvalidated CN."""
    problems: list[str] = []
    gtin = fields.get("01")
    if gtin and re.fullmatch(r"0" + SPAIN_PREFIX + r"\d{7}", gtin):
        candidate = gtin[7:14]
        if cn_module.is_valid(candidate):
            other = fields.get("712")
            if other is not None and other != candidate:
                return NationalCode(None, None, [f"(01) carries CN {candidate} but (712) carries {other!r}: the code contradicts itself"])
            return NationalCode(candidate, "ntin")
        problems.append("check digit of the NTIN does not match its Codigo Nacional")
    elif gtin:
        problems.append("(01) is a regular GTIN, not a Spanish NTIN")
    if "712" in fields:
        candidate = fields["712"]
        if re.fullmatch(r"\d{7}", candidate) and cn_module.is_valid(candidate):
            return NationalCode(candidate, "ai712", problems)
        problems.append(f"(712) is not a valid 7-digit Codigo Nacional: {candidate!r}")
    elif not gtin:
        problems.append("no (01) and no (712) in the code")
    return NationalCode(None, None, problems)


def parse_pack_code(text: str) -> PackCode:
    fields = parse_elements(text)
    expiry = None
    if "17" in fields:
        try:
            expiry = parse_expiry(fields["17"])
        except ValueError:
            expiry = None
    national = national_code(fields)
    if "17" in fields and expiry is None:
        national.problems.append(f"expiry field (17) is not a valid date: {fields['17']!r}")
    return PackCode(fields.get("01"), expiry, fields.get("10"), fields.get("21"), national, fields)
