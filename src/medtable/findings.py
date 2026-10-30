"""Findings the tool can raise, in plain English.

Wording rules: a finding is something to REVIEW with a pharmacist or doctor, never a verdict. There is no "all clear"
finding: the absence of findings is not a statement of safety, and the UI must say which checks were run.
Quotes from the SmPC stay in Spanish on purpose: they are verbatim AEMPS text, checked against the original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NOT_A_FULL_CHECK = "This is not a full interaction check."
NOT_AN_INTERACTION_CHECK = "No mention was found in the sections checked. " + NOT_A_FULL_CHECK

TEMPLATES = {
    "duplicate_ingredient": "{a} and {b} contain the same active ingredient ({detail}). Review with a pharmacist or doctor before using both.",
    "same_medicine_twice": "There are two packs of {a}. Make sure they are not taken together by mistake.",
    "same_atc_class": "{a} and {b} belong to the same pharmacological group ({detail}). To review with a pharmacist.",
    "expired": "{a} expired on {detail}. Do not include it in the calendar without asking a pharmacist.",
    "expires_soon": "{a} expires on {detail}.",
    "smpc_mention": "The official leaflet of {a} (SmPC section 4.5) mentions {detail}: \"{quote}\" To review with a pharmacist. " + NOT_A_FULL_CHECK,
    "meal_note": "The official leaflet of {a} (SmPC section 4.2) says about meals: \"{quote}\" This is a quotation; the schedule is decided by the caregiver with a doctor or pharmacist.",
    "pack_on_several_lines": "The pack {a} appears on several sheet lines ({detail}). Use one line per pack: merge or correct them before continuing.",
    "all_zero_line": "The line \"{detail}\" has no dose at all (all 0), so it is not in the calendar. If this is a mistake, correct it.",
    "expiry_unknown": "The expiry of {a} was not checked: {detail}. Look at the pack.",
    "smpc_unavailable": "Section {detail} of the official leaflet (SmPC) of {a} could not be checked: that check was not done for this medicine.",
    "prescribed_not_found": "Listed on the medication sheet but not found on the table: {detail}.",
    "not_prescribed": "On the table but not on the medication sheet: {a}.",
    "strength_mismatch": "The sheet says \"{detail}\" but the pack is {a}. The strength does not match: check before continuing.",
    "ambiguous_match": "The line \"{detail}\" could match several packs ({a}). Say which one it is.",
    "invalid_dose": "The dose \"{quote}\" on the line \"{detail}\" is not understood. Correct or confirm it.",
    "unverified_item": "This pack could not be verified ({detail}). It is not included in the calendar.",
}

TITLES = {   # short headline for each kind, used by the app cards
    "duplicate_ingredient": "Same active ingredient", "same_medicine_twice": "Two packs of one medicine", "same_atc_class": "Same drug class",
    "expired": "Expired pack", "expires_soon": "Expires soon", "smpc_mention": "Leaflet mentions another pack", "meal_note": "Leaflet note about meals",
    "pack_on_several_lines": "Pack on several lines", "all_zero_line": "Line without doses", "expiry_unknown": "Expiry not checked",
    "smpc_unavailable": "Leaflet section unavailable", "prescribed_not_found": "On the sheet, not on the table", "not_prescribed": "On the table, not on the sheet",
    "strength_mismatch": "Strength does not match", "ambiguous_match": "Line matches several packs", "invalid_dose": "Dose not understood",
    "unverified_item": "Pack not verified",
}


def explain_problem(problem: str) -> str:
    """Friendly wording for the internal reasons a reading could not be verified."""
    known = (
        (r"CIMA has no medicine with CN (\d+)", lambda m: f"AEMPS CIMA does not know the national code {m.group(1)}"),
        (r"not a GS1 element string", lambda m: "the code read is not a GS1 medicine code"),
        (r"check digit of the NTIN", lambda m: "the check digit of the national code is invalid"),
        (r"\(01\) is a regular GTIN", lambda m: "the code does not contain a Spanish national code"),
        (r"\(712\) is not a valid", lambda m: "field 712 is not a valid national code"),
        (r"no \(01\) and no \(712\)", lambda m: "the code holds no medicine data"),
        (r"could not be reached", lambda m: "the official database could not be reached (no internet?): press Try again"),
    )
    for pattern, wording in known:
        match = re.search(pattern, problem)
        if match:
            return wording(match)
    return problem


@dataclass
class Finding:
    kind: str
    names: list[str] = field(default_factory=list)  # display names of the packs involved (1 or 2)
    cns: list[str] = field(default_factory=list)  # CN6 of those packs
    detail: str = ""  # shared ingredient, class, date, sheet line...
    quote: str = ""  # verbatim sentence from the source, when there is one
    source: str = ""  # citation of that source (AEMPS CIMA, date)
    severity: str = "review"  # "review" or "info"

    @property
    def title(self) -> str:
        return TITLES[self.kind]

    def text(self) -> str:
        names = self.names + ["", ""]
        return TEMPLATES[self.kind].format(a=names[0], b=names[1], detail=self.detail, quote=self.quote)

    def lead(self) -> str:
        """The sentence without the quoted passage, for screens that show the quote on its own line."""
        return self.text() if not self.quote else self.text().split(": " + chr(34))[0] + "."
