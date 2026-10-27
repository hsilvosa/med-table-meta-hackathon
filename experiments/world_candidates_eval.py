"""Packs without a visible code, in photos taken in the 3D room: SAM 3 finds the box, the model proposes CIMA candidates.

  .venv-app/Scripts/python.exe experiments/world_candidates_eval.py [N=6] [meta|local]

Takes photos from data/world_photos whose truth lists boxes without a code (and a close camera, <= 0.6 m), runs SAM 3 (as a
subprocess in .venv-sam3), keeps the SAM box that contains the truth box centre and asks `candidates.propose` for candidates.
Reports whether the true medicine is the first candidate or within the first four. Costs about USD 0.005 per crop with the
Meta backend. The crops come from official CIMA photos, so this says how well text reading plus CIMA search work, not how
real photos behave; the caregiver always confirms the pick.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from medtable import candidates  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
backend = sys.argv[2] if len(sys.argv) > 2 else None
resolver = Resolver("data/cache/cima")


def norm(nregistro: str) -> int:
    return int("".join(c for c in str(nregistro) if c.isdigit()) or 0)


jobs = []
for meta in sorted(Path("data/world_photos").glob("photo_*.json")):
    truth = json.loads(meta.read_text(encoding="utf-8"))
    if truth["boxes_without_code"] and truth["distance_m"] <= 0.6:
        jobs.append((meta.with_suffix(".jpg"), truth))
jobs = jobs[:n]
top1 = top4 = total = empty = 0
for photo, truth in jobs:
    folder = Path("data/cache/world_segments") / photo.stem
    folder.mkdir(parents=True, exist_ok=True)
    boxes = candidates.segment(photo, folder)
    for want in truth["boxes_without_code"]:
        x, y = want["px"]
        box = next((b for b in boxes if b.bbox[0] <= x <= b.bbox[2] and b.bbox[1] <= y <= b.bbox[3]), None)
        total += 1
        if box is None:
            print(f"{photo.name}: SAM found no box at {want['px']} for {want['name'][:30]}")
            empty += 1
            continue
        proposal = candidates.propose(box.crop, resolver, backend)
        ids = [norm(c.medicine.nregistro) for c in proposal.candidates]
        hit1, hit4 = bool(ids) and ids[0] == norm(want["nregistro"]), norm(want["nregistro"]) in ids
        top1 += hit1
        top4 += hit4
        print(f"{want['name'][:36]:36} crop {box.crop.name} read={str((proposal.read or {}).get('marca'))[:22]:22} top1={hit1} top4={hit4} n={len(ids)}")
print(f"photos {len(jobs)}; boxes without code {total}; SAM missed {empty}; truth first {top1}, within four {top4}")
