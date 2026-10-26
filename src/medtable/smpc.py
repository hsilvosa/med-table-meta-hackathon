"""SmPC (ficha tecnica) sections from AEMPS CIMA, cached, with verbatim sentence search.

Used for two things only, always as quotations with their source and never as a verdict:
  * section 4.5 (interactions): sentences that name another pack's active ingredient or pharmacological class;
  * section 4.2 (posology): sentences that say how the medicine relates to meals.
A quote is returned only if it is an exact substring of the fetched section text.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
import urllib.error
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import cima

SECTION_URL = cima.API + "/docSegmentado/contenido/1?nregistro={nregistro}&seccion={section}"
FT_URL = "https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FT_{nregistro}.html"
MEAL_TERMS = ("con las comidas", "con comida", "con alimentos", "con o sin alimentos", "con o sin comida", "en ayunas",
              "antes de las comidas", "antes de comer", "despues de las comidas", "despues de comer", "estomago vacio",
              "durante las comidas", "con el desayuno", "con la cena")


@dataclass
class Section:
    nregistro: str
    section: str
    text: str
    fetched: str

    def citation(self) -> str:
        return f"AEMPS CIMA, ficha tecnica (nregistro {self.nregistro}), section {self.section}, consulted {self.fetched}: " \
               f"{FT_URL.format(nregistro=self.nregistro)}"


def plain(text: str) -> str:
    """Accent-free lower case with single spaces; used only for matching, never for quotes."""
    folded = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", folded).strip()


def stem_words(text: str) -> str:
    """Crude Spanish plural stripping so that 'inhibidor' matches 'inhibidores'."""
    out = []
    for w in re.findall(r"[a-z0-9]+", plain(text)):
        out.append(w[:-2] if w.endswith("es") and len(w) > 5 else w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return " ".join(out)


def sentences(text: str) -> list[str]:
    """Split on full stops, semicolons and colons followed by a capital or bracket; every piece is an exact substring."""
    parts = re.split(r"(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚÑ(¿¡])", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def find_mentions(text: str, terms: list[str], *, max_per_term: int = 2) -> list[tuple[str, str]]:
    """(term, sentence) pairs: sentences of `text` that contain the term as whole words (accent/plural insensitive)."""
    found = []
    for term in terms:
        wanted = f" {stem_words(term)} "
        hits = [s for s in sentences(text) if wanted in f" {stem_words(s)} "]
        found += [(term, s) for s in hits[:max_per_term]]
    return found


def meal_sentences(text: str) -> list[str]:
    return [s for s in sentences(text) if any(t in plain(s) for t in MEAL_TERMS)]


class Smpc:
    def __init__(self, cache_dir: Path | str = "data/cache/smpc") -> None:
        self.cache_dir = Path(cache_dir)

    def section(self, nregistro: str, section: str) -> Section | None:
        """Text of one SmPC section ('4.2', '4.5'...). None when CIMA has no such section for the medicine."""
        cached = self.cache_dir / f"{nregistro}_{section}.json"
        if cached.exists():
            return Section(**json.loads(cached.read_text(encoding="utf-8")))
        try:
            raw = cima.fetch(SECTION_URL.format(nregistro=nregistro, section=section)).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
        if not text:
            return None
        result = Section(nregistro, section, text, date.today().isoformat())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(result.__dict__, ensure_ascii=False), encoding="utf-8")
        return result
