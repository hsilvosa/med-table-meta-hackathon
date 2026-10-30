"""Packs without a readable code: SAM finds them, a vision model proposes candidates, the caregiver confirms.

Nothing in this module identifies a medicine. SAM returns boxes; the model's reading is only a search query for
AEMPS CIMA; the candidates are shown with their official photo and nothing enters the plan until a person picks one.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import cima, cn, vlm
from .decode import Detection
from .resolve import Medicine, Resolver

CROP_PROMPT = ('This is a cropped photo of a Spanish medicine box. Read ONLY what is printed on it. '
               'Answer with JSON: {"marca": str|null, "principio_activo": str|null, "dosis": str|null, '
               '"forma": str|null, "codigo_nacional": str|null} (brand, active ingredient, strength, form, national code, as printed, in Spanish). '
               'Use null when it is not clearly legible. Do not guess.')


@dataclass
class Box:
    crop: Path
    bbox: tuple[int, int, int, int]
    score: float


def segment(photo: Path, out_dir: Path, sam_python: str | None = None, timeout: int = 600) -> list[Box]:
    """Run SAM 3 in its own environment (it needs torch and a GPU) and read back the boxes."""
    python = sam_python or os.environ.get("SAM_PYTHON", ".venv-sam3/Scripts/python.exe")
    done = subprocess.run([python, "scripts/segment_boxes.py", str(photo), str(out_dir)], capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"SAM 3 failed: {done.stderr.strip().splitlines()[-1] if done.stderr.strip() else 'no output'}")
    items = json.loads((out_dir / "boxes.json").read_text(encoding="utf-8"))
    return [Box(out_dir / i["crop"], tuple(i["bbox"]), i["score"]) for i in items]


def boxes_without_code(boxes: list[Box], detections: list[Detection]) -> list[Box]:
    """Boxes that contain the centre of no decoded Data Matrix: these packs were not identified by their code."""
    def contains(box: Box, d: Detection) -> bool:
        cx, cy = (d.bbox[0] + d.bbox[2]) / 2, (d.bbox[1] + d.bbox[3]) / 2
        return box.bbox[0] <= cx <= box.bbox[2] and box.bbox[1] <= cy <= box.bbox[3]
    return [b for b in boxes if not any(contains(b, d) for d in detections)]


def fold(text: object) -> str:
    folded = unicodedata.normalize("NFD", str(text or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in folded if unicodedata.category(c) != "Mn")).strip()


@dataclass
class Candidate:
    medicine: Medicine
    score: float
    why: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    read: dict  # what the model says it saw (a search query, not an identification)
    candidates: list[Candidate]
    cn_checked: str | None = None  # a CN read from the box that passed check digit and exists in CIMA
    note: str = ""


def _search_terms(read: dict) -> list[tuple[str, str]]:
    terms = []
    if read.get("marca"):
        terms.append(("nombre", str(read["marca"])))
    if read.get("principio_activo"):
        terms.append(("practiv1", str(read["principio_activo"])))
    return terms


def score_candidate(medicine: Medicine, read: dict) -> Candidate:
    name = fold(medicine.name)
    score, why = 0.0, []
    brand = fold(read.get("marca"))
    if brand and brand.split()[0] in name.split():
        score += 2
        why.append("brand matches")
    ingredient = fold(read.get("principio_activo"))
    if ingredient and any(ingredient.split()[0][:6] in fold(i) for i in medicine.active_ingredients):
        score += 2
        why.append("active ingredient matches")
    numbers = set(re.findall(r"\d+(?:[.,]\d+)?", str(read.get("dosis") or "")))
    if numbers and numbers <= set(re.findall(r"\d+(?:[.,]\d+)?", medicine.name)):
        score += 1
        why.append("strength matches")
    return Candidate(medicine, score, why)


def propose(crop: Path, resolver: Resolver, backend: str | None = None, limit: int = 4, consent: bool = False) -> Proposal:
    """Ask the model what is printed on the crop, then search CIMA with that text and rank the answers."""
    reply = vlm.ask_image(crop, CROP_PROMPT, backend=backend, max_tokens=500, note="crop reader", consent=consent)
    read = vlm.parse_json(reply.text)
    if not isinstance(read, dict):
        return Proposal({}, [], note="The model could not read anything in the crop.")
    proposal = Proposal(read, [])
    found = cn.find_cn(str(read.get("codigo_nacional") or ""))
    if found and cn.is_valid(found):
        medicine = resolver.by_cn(found)
        if medicine:
            proposal.cn_checked = found
            lead = score_candidate(medicine, read)
            lead.score += 1.5
            lead.why.insert(0, "a model read this code on the box: check it yourself")
            proposal.candidates.append(lead)
    seen = {c.medicine.nregistro for c in proposal.candidates}
    for param, value in _search_terms(read):
        for item in cima.get_json("medicamentos", comerc=1, **{param: value}).get("resultados", [])[:limit]:
            if item["nregistro"] in seen:
                continue
            seen.add(item["nregistro"])
            full = cima.medicine_by_nregistro(item["nregistro"])
            presentation = next((p for p in full.get("presentaciones", []) if p.get("cn")), None)
            medicine = resolver.by_cn(presentation["cn"]) if presentation else None
            if medicine:
                proposal.candidates.append(score_candidate(medicine, read))
    proposal.candidates.sort(key=lambda c: -c.score)
    del proposal.candidates[limit:]
    if not proposal.candidates:
        proposal.note = "CIMA has no candidates for what is visible in the crop."
    return proposal
