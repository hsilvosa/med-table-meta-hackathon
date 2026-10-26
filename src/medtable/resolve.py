"""Resolve a Codigo Nacional in AEMPS CIMA, with a local JSON cache (data/cache/cima/<cn6>.json).

Every Medicine carries the source URL and the date it was fetched, so each claim built on it can cite AEMPS/CIMA.
The cache also lets the app keep working offline for medicines it has seen before.
"""

from __future__ import annotations

import json
import urllib.error
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from . import cima

DETAIL_URL = "https://cima.aemps.es/cima/publico/detalle.html?nregistro={}"


@dataclass
class Medicine:
    cn: str  # 6 digits, as CIMA lists them
    nregistro: str
    name: str
    active_ingredients: list[str]
    strengths: list[dict]  # [{"nombre": "BRINZOLAMIDA", "cantidad": "10", "unidad": "mg"}, ...] as listed by CIMA
    atc: list[dict]  # [{"codigo": "S01EC04", "nombre": "Brinzolamida", "nivel": 5}, ...]
    form: str | None
    presentation: str | None  # the specific pack that matched the CN
    marketed: bool | None
    holder: str | None
    photos: dict[str, str] = field(default_factory=dict)  # tipo -> full-size URL
    docs: dict[str, str] = field(default_factory=dict)  # "ficha_tecnica" / "prospecto" -> HTML URL
    source_url: str = ""
    fetched: str = ""  # ISO date of the CIMA query

    def citation(self) -> str:
        return f"AEMPS CIMA, {self.name} (nregistro {self.nregistro}), consultado el {self.fetched}: {self.source_url}"

    def atc_code(self, level: int) -> str | None:
        return next((a["codigo"] for a in self.atc if a.get("nivel") == level), None)


def _from_cima(cn6: str, d: dict, fetched: str) -> Medicine:
    presentation = next((p["nombre"] for p in d.get("presentaciones", []) if p.get("cn") == cn6), None)
    docs = {"ficha_tecnica": None, "prospecto": None}
    for doc in d.get("docs", []):
        key = {1: "ficha_tecnica", 2: "prospecto"}.get(doc.get("tipo"))
        if key and doc.get("urlHtml"):
            docs[key] = doc["urlHtml"]
    return Medicine(
        cn=cn6, nregistro=d["nregistro"], name=d["nombre"],
        active_ingredients=[p["nombre"] for p in d.get("principiosActivos", [])],
        strengths=[{k: p.get(k) for k in ("nombre", "cantidad", "unidad")} for p in d.get("principiosActivos", [])],
        atc=d.get("atcs", []), form=(d.get("formaFarmaceutica") or {}).get("nombre"),
        presentation=presentation, marketed=d.get("comerc"), holder=d.get("labtitular"),
        photos={p["tipo"]: cima.full_size_url(p["url"]) for p in d.get("fotos", [])},
        docs={k: v for k, v in docs.items() if v}, source_url=DETAIL_URL.format(d["nregistro"]), fetched=fetched)


class Resolver:
    def __init__(self, cache_dir: Path | str = "data/cache/cima") -> None:
        self.cache_dir = Path(cache_dir)

    def by_cn(self, cn: str) -> Medicine | None:
        """`cn` may be 6 or 7 digits (the check digit is ignored). None when CIMA does not know the CN."""
        cn6 = "".join(ch for ch in cn if ch.isdigit())[:6]
        cached = self.cache_dir / f"{cn6}.json"
        if cached.exists():
            stored = json.loads(cached.read_text(encoding="utf-8"))
            if "strengths" in stored:  # entries written by an older version lack it: fetch again
                return Medicine(**stored)
        try:
            data = cima.medicine_by_cn(cn6)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if not data or "nregistro" not in data:
            return None
        medicine = _from_cima(cn6, data, date.today().isoformat())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(asdict(medicine), ensure_ascii=False, indent=1), encoding="utf-8")
        return medicine
