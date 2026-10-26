"""Findings the tool can raise, with their Spanish and English wording.

Wording rules: a finding is something to REVIEW with a pharmacist or doctor, never a verdict. There is no "all clear"
finding: the absence of findings is not a statement of safety, and the UI must say which checks were run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NOT_AN_INTERACTION_CHECK = {
    "es": "No se encontró ninguna mención en las secciones revisadas. Esto no es una comprobación completa de interacciones.",
    "en": "No mention was found in the sections checked. This is not a full interaction check.",
}

TEMPLATES = {
    "duplicate_ingredient": {
        "es": "{a} y {b} contienen el mismo principio activo ({detail}). Revíselo con su farmacéutico o médico antes de usar ambos.",
        "en": "{a} and {b} contain the same active ingredient ({detail}). Review with a pharmacist or doctor before using both."},
    "same_medicine_twice": {
        "es": "Hay dos envases de {a}. Compruebe que no se toman a la vez por error.",
        "en": "There are two packs of {a}. Make sure they are not taken together by mistake."},
    "same_atc_class": {
        "es": "{a} y {b} pertenecen al mismo grupo farmacológico ({detail}). Para revisar con su farmacéutico.",
        "en": "{a} and {b} belong to the same pharmacological group ({detail}). To review with a pharmacist."},
    "expired": {
        "es": "{a} caducó el {detail}. No lo incluya en el calendario sin consultar a su farmacéutico.",
        "en": "{a} expired on {detail}. Do not include it in the calendar without asking a pharmacist."},
    "expires_soon": {
        "es": "{a} caduca el {detail}.",
        "en": "{a} expires on {detail}."},
    "smpc_mention": {
        "es": "La ficha técnica de {a} (sección 4.5) menciona {detail}: «…{quote}…». Para revisar con su farmacéutico; no es una comprobación completa de interacciones.",
        "en": "The SmPC of {a} (section 4.5) mentions {detail}: \"...{quote}...\". To review with a pharmacist; not a full interaction check."},
    "prescribed_not_found": {
        "es": "Figura en la hoja de medicación pero no se ha encontrado en la mesa: {detail}.",
        "en": "Listed on the medication sheet but not found on the table: {detail}."},
    "not_prescribed": {
        "es": "Está en la mesa pero no figura en la hoja de medicación: {a}.",
        "en": "On the table but not on the medication sheet: {a}."},
    "strength_mismatch": {
        "es": "La hoja dice «{detail}» pero el envase es {a}. La dosis no coincide: compruébelo antes de continuar.",
        "en": "The sheet says \"{detail}\" but the pack is {a}. The strength does not match: check before continuing."},
    "ambiguous_match": {
        "es": "La línea «{detail}» podría corresponder a varios envases ({a}). Indique cuál es.",
        "en": "The line \"{detail}\" could match several packs ({a}). Say which one it is."},
    "invalid_dose": {
        "es": "La dosis «{quote}» de la línea «{detail}» no se entiende. Corríjala o confírmela.",
        "en": "The dose \"{quote}\" on the line \"{detail}\" is not understood. Correct or confirm it."},
    "unverified_item": {
        "es": "No se pudo verificar este envase ({detail}). No entra en el calendario.",
        "en": "This pack could not be verified ({detail}). It is not included in the calendar."},
}


@dataclass
class Finding:
    kind: str
    names: list[str] = field(default_factory=list)  # display names of the packs involved (1 or 2)
    cns: list[str] = field(default_factory=list)  # CN6 of those packs
    detail: str = ""  # shared ingredient, class, date, sheet line...
    quote: str = ""  # verbatim sentence from the source, when there is one
    source: str = ""  # citation of that source (AEMPS CIMA, date)
    severity: str = "review"  # "review" or "info"

    def text(self, lang: str = "es") -> str:
        names = self.names + ["", ""]
        return TEMPLATES[self.kind][lang].format(a=names[0], b=names[1], detail=self.detail, quote=self.quote)
