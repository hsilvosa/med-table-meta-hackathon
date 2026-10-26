"""Checks that need only the packs on the table (and their SmPC text): duplicates, class overlap, expiry, 4.5 mentions.

Every finding is something to review with a pharmacist; none is a verdict. The 4.5 check is a text search, not an
interaction database: it quotes sentences of one medicine's SmPC that name another pack's active ingredient or
pharmacological class, and the quote is always an exact substring of the AEMPS text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations, permutations
from typing import Protocol

from .findings import Finding
from .identify import Reading
from .resolve import Medicine
from .smpc import ELLIPSIS, Section, find_mentions, plain

class SectionSource(Protocol):
    """Anything that returns SmPC sections: the cached CIMA client, or a stand-in in tests."""

    def section(self, nregistro: str, section: str) -> Section | None: ...


NEGATIONS = ("no se han descrito", "no se ha descrito", "no se han observado", "no se ha observado", "no se han realizado", "no interacciona")
GENERIC_WORDS = {"acido", "sodico", "potasico", "calcico", "magnesico", "hidrocloruro", "clorhidrato", "sulfato",
                 "maleato", "besilato", "tartrato", "succinato", "fosfato", "citrato"}


@dataclass
class Pack:
    medicine: Medicine
    state: str = "verified"  # "verified" (decoded code) or "confirmed" (picked by the user next to the official photo)
    expiry: date | None = None


def packs_from_readings(readings: list[Reading]) -> tuple[list[Pack], list[Finding]]:
    """Verified readings become packs; everything else becomes an 'unverified_item' finding and stays out of the plan."""
    packs, findings = [], []
    for r in readings:
        if r.status == "verified" and r.medicine:
            packs.append(Pack(r.medicine, "verified", r.expiry))
        else:
            findings.append(Finding("unverified_item", detail="; ".join(r.problems) or "unknown"))
    return packs, findings


def ingredient_keys(medicine: Medicine) -> set[str]:
    """One comparable key per active ingredient: its first significant word (salts and 'acido' do not count)."""
    keys = set()
    for name in medicine.active_ingredients:
        words = [w for w in re.findall(r"[a-z]+", plain(name)) if w not in GENERIC_WORDS and len(w) >= 5]
        if words:
            keys.add(words[0])
    return keys


def _clean_class_name(name: str) -> str:
    return re.sub(r"\d+\)\s*$", "", name).strip()


def mention_terms(medicine: Medicine) -> list[str]:
    """What another medicine's SmPC would have to say to name this one: its ingredients and its class names."""
    terms = [n for n in medicine.active_ingredients if len(n) >= 5]
    for atc in medicine.atc:
        if atc.get("nivel") in (3, 4):
            name = _clean_class_name(atc.get("nombre", ""))
            if len(name.split()) >= 2 and len(name) >= 12:
                terms.append(name)
    return terms


def check_packs(packs: list[Pack], smpc: SectionSource | None = None, today: date | None = None, soon_days: int = 30) -> list[Finding]:
    today = today or date.today()
    findings: list[Finding] = []

    for pack in packs:  # expiry comes straight from the pack's code
        if pack.expiry and pack.expiry < today:
            findings.append(Finding("expired", [pack.medicine.name], [pack.medicine.cn], pack.expiry.isoformat(),
                                    source=pack.medicine.citation()))
        elif pack.expiry and pack.expiry <= today + timedelta(days=soon_days):
            findings.append(Finding("expires_soon", [pack.medicine.name], [pack.medicine.cn], pack.expiry.isoformat(), severity="info"))

    by_cn: dict[str, list[Pack]] = {}
    for pack in packs:
        by_cn.setdefault(pack.medicine.cn, []).append(pack)
    for cn6, same in by_cn.items():
        if len(same) > 1:
            findings.append(Finding("same_medicine_twice", [same[0].medicine.name], [cn6], severity="info"))
    distinct = [same[0].medicine for same in by_cn.values()]

    duplicated: set[frozenset[str]] = set()
    for a, b in combinations(distinct, 2):
        shared_atc = {x["codigo"] for x in a.atc if x.get("nivel") == 5} & {x["codigo"] for x in b.atc if x.get("nivel") == 5}
        shared_names = ingredient_keys(a) & ingredient_keys(b)
        if shared_atc or shared_names:
            detail = ", ".join(sorted(shared_names)) or ", ".join(sorted(shared_atc))
            findings.append(Finding("duplicate_ingredient", [a.name, b.name], [a.cn, b.cn], detail, source=a.citation()))
            duplicated.add(frozenset((a.cn, b.cn)))
            continue
        class_a = {x["codigo"]: x["nombre"] for x in a.atc if x.get("nivel") == 4}
        class_b = {x["codigo"] for x in b.atc if x.get("nivel") == 4}
        for code in sorted(set(class_a) & class_b):
            findings.append(Finding("same_atc_class", [a.name, b.name], [a.cn, b.cn], f"{code} {_clean_class_name(class_a[code])}",
                                    source=a.citation()))

    if smpc is not None:  # section 4.5 quotations, both directions of every pair
        for a, b in permutations(distinct, 2):
            if frozenset((a.cn, b.cn)) in duplicated:
                continue  # already flagged: A's SmPC naming its own ingredient adds nothing
            section = smpc.section(a.nregistro, "4.5")
            if not section:
                continue
            for term, sentence in find_mentions(section.text, mention_terms(b)):
                assert all(part in section.text for part in sentence.split(ELLIPSIS))  # a quote is made of exact fragments of the AEMPS text
                negated = any(n in plain(sentence) for n in NEGATIONS)  # "no se han descrito interacciones con X": quoted, but informative
                findings.append(Finding("smpc_mention", [a.name, b.name], [a.cn, b.cn], term, sentence, section.citation(),
                                        "info" if negated else "review"))
    return findings
