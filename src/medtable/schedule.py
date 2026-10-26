"""The medication sheet: lines with doses per moment of the day, reconciled against the packs on the table.

Doses are copied exactly as written on the sheet (or typed by the caregiver) and are never rewritten by a model. A
line enters the calendar only after the caregiver confirms it AND it matches a verified pack without blocking
findings. Everything else is listed as "not included" with the reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .findings import Finding
from .rules import GENERIC_WORDS, Pack, ingredient_keys
from .smpc import plain, stem_words

SLOTS = ("desayuno", "comida", "cena", "acostarse")
DOSE_RE = re.compile(r"^(?:\d{1,2}(?:[.,]\d{1,2})?|\d/\d)$")  # 0, 1, 2, 0,5, 1/2, 3/4
FORM_WORDS = {"comprimidos", "comprimido", "capsulas", "capsula", "efg", "recubiertos", "pelicula", "solucion", "sobres", "gotas"}
NON_SOLID_FORMS = ("suspension", "solucion", "jarabe", "colirio", "crema", "gel", "inyect", "gotas", "pomada", "spray", "emulsion", "polvo", "parche", "inhal", "ungüento", "unguento", "enema", "supositorio", "granulado")
MASS_TO_MG = {"mg": 1.0, "g": 1000.0, "mcg": 0.001, "ug": 0.001, "µg": 0.001, "microgramos": 0.001, "gr": 1000.0}


@dataclass
class Line:
    text: str  # medicine as written on the sheet
    doses: dict[str, str] = field(default_factory=dict)  # slot -> dose as written ("1", "1/2", "0")
    remarks: str = ""
    cn: str | None = None  # when the caregiver typed or picked the exact pack
    confirmed: bool = False  # the caregiver has checked this line

    def active_slots(self) -> list[tuple[str, str]]:
        return [(s, d) for s, d in ((s, self.doses.get(s, "0").strip()) for s in SLOTS) if dose_number(d) != 0]


def dose_number(dose: str) -> float | None:
    """Numeric value of a dose string; None when it is not a recognised dose."""
    dose = dose.strip()
    if not DOSE_RE.match(dose):
        return None
    if "/" in dose:
        num, den = dose.split("/")
        return float(num) / float(den) if float(den) else None
    return float(dose.replace(",", "."))


def lines_from_rows(rows: list[dict]) -> tuple[list[Line], list[Finding]]:
    """Rows as returned by the sheet reader (or a form). Lines start unconfirmed; unreadable doses raise a finding."""
    lines, findings = [], []
    for row in rows:
        line = Line(str(row.get("medicamento", "")).strip(), {s: str(row.get(s, "") or "0").strip() for s in SLOTS},
                    str(row.get("observaciones", "") or "").strip(), row.get("cn"))
        for slot, dose in line.doses.items():
            if dose_number(dose) is None:
                findings.append(Finding("invalid_dose", detail=line.text, quote=dose))
        lines.append(line)
    return lines, findings


def _numbers(text: str) -> list[float]:
    """Strengths in a text, in mg when a mass unit follows: '160/12,5 mg' -> [12.5, 160.0]; '1 g' -> [1000.0]."""
    out = []
    for value, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(mg|g|mcg|µg|ug|gr)?\b", text.lower()):
        number = float(value.replace(",", "."))
        out.append(round(number * MASS_TO_MG.get(unit, 1.0), 6))
    return sorted(out)


def strength_matches(line: Line, pack: Pack) -> bool | None:
    """True/False when both sides state strengths; None when either side has none to compare.

    Only solid single-dose forms are compared: for liquids, creams, drops and the like CIMA lists the amount per container
    while names and sheets give a concentration (20 mg/ml), so the numbers are not comparable and no verdict is given.
    """
    form = plain(pack.medicine.form or "")
    if any(word in form for word in NON_SOLID_FORMS) or re.search(r"/\s*(ml|l|dosis|gota|g)\b", line.text.lower()):
        return None
    wanted = _numbers(line.text)
    actual = sorted(round(float(str(s["cantidad"]).replace(",", ".")) * MASS_TO_MG.get(str(s["unidad"]).lower(), 1.0), 6)
                    for s in pack.medicine.strengths if s.get("cantidad") not in (None, ""))
    return None if not wanted or not actual else wanted == actual


def _score(line: Line, pack: Pack) -> int:
    """How many of the pack's ingredient names (or its brand) appear in the line text."""
    tokens = set(stem_words(line.text).split())
    keys = {stem_words(k) for k in ingredient_keys(pack.medicine)}
    brand = stem_words(pack.medicine.name.split()[0]) if pack.medicine.name else ""
    score = len(keys & tokens)
    if brand and brand in tokens and brand not in GENERIC_WORDS and plain(brand) not in FORM_WORDS:
        score += 1
    return score


@dataclass
class Reconciliation:
    matches: dict[int, Pack]  # line index -> pack
    findings: list[Finding]
    blocked: dict[int, str]  # line index -> reason it cannot enter the calendar


def reconcile(lines: list[Line], packs: list[Pack]) -> Reconciliation:
    matches: dict[int, Pack] = {}
    findings: list[Finding] = []
    blocked: dict[int, str] = {}
    for i, line in enumerate(lines):
        if line.cn:
            candidates = [p for p in packs if p.medicine.cn == line.cn[:6]]
        else:
            scored = [(_score(line, p), p) for p in packs]
            best = max((s for s, _ in scored), default=0)
            candidates = [p for s, p in scored if s == best and best > 0]
            exact = [p for p in candidates if strength_matches(line, p)]
            candidates = exact or candidates  # prefer the pack whose strength agrees with the line
        distinct = {p.medicine.cn: p for p in candidates}
        if not distinct:
            findings.append(Finding("prescribed_not_found", detail=line.text))
            blocked[i] = "no hay ningún envase en la mesa"
        elif len(distinct) > 1:
            findings.append(Finding("ambiguous_match", [p.medicine.name for p in distinct.values()], list(distinct), line.text))
            blocked[i] = "varios envases encajan; indique cuál es"
        else:
            pack = next(iter(distinct.values()))
            matches[i] = pack
            if strength_matches(line, pack) is False:
                findings.append(Finding("strength_mismatch", [pack.medicine.name], [pack.medicine.cn], line.text, source=pack.medicine.citation()))
                blocked[i] = "la dosis de la hoja no coincide con el envase"
    by_pack: dict[str, list[int]] = {}
    for i, pack in matches.items():
        by_pack.setdefault(pack.medicine.cn, []).append(i)
    for cn6, indexes in by_pack.items():
        if len(indexes) > 1:
            findings.append(Finding("pack_on_several_lines", [matches[indexes[0]].medicine.name], [cn6],
                                    "; ".join(lines[i].text for i in indexes), source=matches[indexes[0]].medicine.citation()))
            for i in indexes:
                blocked[i] = "el envase está en varias líneas; deje una sola"
    for i, line in enumerate(lines):
        if i in matches and i not in blocked and line.doses and not line.active_slots() and all(dose_number(d) is not None for d in line.doses.values()):
            findings.append(Finding("all_zero_line", detail=line.text))
            blocked[i] = "la línea no tiene ninguna dosis"
    matched_cns = {p.medicine.cn for p in matches.values()} | {c for f in findings if f.kind == "ambiguous_match" for c in f.cns}
    seen: set[str] = set()
    for pack in packs:
        if pack.medicine.cn not in matched_cns and pack.medicine.cn not in seen:
            seen.add(pack.medicine.cn)
            findings.append(Finding("not_prescribed", [pack.medicine.name], [pack.medicine.cn]))
    return Reconciliation(matches, findings, blocked)
