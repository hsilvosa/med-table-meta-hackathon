"""Cut packs and dosage forms out of the CIMA studio photos as transparent PNGs, using SAM 3 text prompts.

  python scripts/make_cutouts.py [--n 50 --seed 0 | --all | --only 73300,68167] [--out data/cutouts]      (needs .venv-sam3 and a GPU)

Packs (`materialas` photos) are found with the prompt "box"; dosage forms (`formafarmac` photos) with
"pill" / "tablet" / "capsule". Every candidate mask must pass sanity checks (size, border contact,
solidity, aspect, not a grey ruler piece, not blank background). Rejected cut-outs are written to
rejected.jsonl with the reason; nothing doubtful is silently kept.

Output: <out>/{box,pill}/<nregistro>_<k>.png, index.jsonl, rejected.jsonl, contact_sheet_{box,pill}.jpg
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from sam3.model.sam3_image_processor import Sam3Processor
from sam3.model_builder import build_sam3_image_model

ORAL_SOLID = re.compile(r"comprimid|c[aá]psula|grageas?|pastilla|p[ií]ldora", re.I)
MAX_SIDE = 1280  # some CIMA photos are 5000 px wide; SAM 3 and the sprites do not need that


def load_photo(path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    scale = MAX_SIDE / max(img.shape[:2])
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img


def find_masks(proc: Sam3Processor, img_bgr: np.ndarray, prompt: str, min_score: float = 0.5):
    """Return [(mask uint8 0/255, score)] for every instance SAM 3 finds for the text prompt."""
    state = proc.set_image(Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)))
    out = proc.set_text_prompt(state=state, prompt=prompt)
    masks = out["masks"][:, 0].cpu().numpy().astype(np.uint8) * 255
    scores = out["scores"].float().cpu().numpy()
    return [(m, float(s)) for m, s in zip(masks, scores) if s >= min_score]


def tidy(mask: np.ndarray, k: int) -> np.ndarray:
    """Open away speckle, keep the largest blob, fill its holes."""
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return mask
    blob = (labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8) * 255
    contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(blob)
    cv2.drawContours(filled, contours, -1, 255, cv2.FILLED)
    return filled


def border_colour_distance(img_bgr: np.ndarray) -> np.ndarray:
    """Lab distance of every pixel to the median colour of the image border (the studio background)."""
    lab = cv2.cvtColor(cv2.GaussianBlur(img_bgr, (3, 3), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    ring = np.concatenate([lab[:6].reshape(-1, 3), lab[-6:].reshape(-1, 3),
                           lab[:, :6].reshape(-1, 3), lab[:, -6:].reshape(-1, 3)])
    return np.linalg.norm(lab - np.median(ring, axis=0), axis=2)


def reject_reason(mask: np.ndarray, img_bgr: np.ndarray, *, pill: bool) -> str | None:
    h, w = mask.shape
    area = int((mask > 0).sum())
    frac = area / (h * w)
    lo, hi = (0.004, 0.25) if pill else (0.03, 0.90)
    if not lo <= frac <= hi:
        return f"area_fraction={frac:.4f}"
    ys, xs = np.where(mask > 0)
    if pill and (xs.min() <= 2 or ys.min() <= 2 or xs.max() >= w - 3 or ys.max() >= h - 3):
        return "touches_border"  # the physical ruler runs off the photo, pills do not
    if pill and max(np.ptp(xs), np.ptp(ys)) > 0.6 * w:
        return "too_wide"
    contour = max(cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
    solidity = area / max(cv2.contourArea(cv2.convexHull(contour)), 1)
    if solidity < (0.92 if pill else 0.80):
        return f"solidity={solidity:.2f}"
    if pill:
        (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
        if max(rw, rh) / max(min(rw, rh), 1) > 5:
            return "aspect>5"
        inner = cv2.erode(mask, np.ones((7, 7), np.uint8)) > 0
        if inner.sum() < 50:
            inner = mask > 0
        dist, hsv = border_colour_distance(img_bgr), cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        if dist[inner].mean() < 1.0 and dist[inner].std() < 0.6:
            return "blank_background"
        if hsv[..., 2][inner].mean() < 170 and hsv[..., 1][inner].mean() < 30:
            return "grey_ruler"
    return None


def drop_overlaps(masks: list[np.ndarray]) -> list[np.ndarray]:
    """When two masks share more than 60% of the smaller one, keep the larger (sub-parts of a pill)."""
    kept: list[np.ndarray] = []
    for m in sorted(masks, key=lambda x: -int((x > 0).sum())):
        if not any(((m > 0) & (k > 0)).sum() > 0.6 * min((m > 0).sum(), (k > 0).sum()) for k in kept):
            kept.append(m)
    return kept


def to_rgba(img_bgr: np.ndarray, mask: np.ndarray, pad: int = 4) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, img_bgr.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, img_bgr.shape[1])
    alpha = cv2.GaussianBlur(mask, (3, 3), 0)  # soft one-pixel edge
    return np.dstack([img_bgr, alpha])[y0:y1, x0:x1]


def cut_box(proc, img):
    found = find_masks(proc, img, "box")
    if not found:
        return [], "no_detection"
    mask = tidy(max(found, key=lambda f: f[1])[0], 9)
    reason = reject_reason(mask, img, pill=False)
    return ([] if reason else [to_rgba(img, mask)]), reason


def cut_pills(proc, img):
    candidates, reasons = [], []
    for prompt in ("pill", "tablet", "capsule"):
        for mask, _ in find_masks(proc, img, prompt):
            mask = tidy(mask, 5)
            reason = reject_reason(mask, img, pill=True)
            (reasons.append(reason) if reason else candidates.append(mask))
    kept = drop_overlaps(candidates)
    return [to_rgba(img, m) for m in kept], (None if kept else ";".join(sorted(set(reasons))) or "no_detection")


def contact_sheet(paths: list[Path], dest: Path, cell: int = 150, cols: int = 10) -> None:
    """Grid of cut-outs over green so that holes and bites are obvious when reviewed by eye."""
    sheet = np.full((max((len(paths) + cols - 1) // cols, 1) * cell, cols * cell, 3), 90, np.uint8)
    for k, p in enumerate(paths):
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        s = (cell - 8) / max(im.shape[:2])
        im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        a = im[..., 3:4] / 255.0
        tile = (im[..., :3] * a + np.array([60, 160, 60]) * (1 - a)).astype(np.uint8)
        r, c = divmod(k, cols)
        sheet[r * cell + 4:r * cell + 4 + tile.shape[0], c * cell + 4:c * cell + 4 + tile.shape[1]] = tile
    cv2.imwrite(str(dest), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated nregistro list: cut out exactly these medicines")
    ap.add_argument("--cima", type=Path, default=Path("data/cima"))
    ap.add_argument("--out", type=Path, default=Path("data/cutouts"))
    a = ap.parse_args()

    meds = [json.loads(line) for line in (a.cima / "manifest.jsonl").open(encoding="utf-8")]
    meds = [m for m in meds if {f["tipo"] for f in m["fotos"]} >= {"materialas", "formafarmac"}]
    if a.only:
        wanted = a.only.split(",")
        meds = [m for m in meds if m["nregistro"] in wanted]
        meds.sort(key=lambda m: wanted.index(m["nregistro"]))      # keep the order given: the room places them in that order
    elif not a.all:
        random.Random(a.seed).shuffle(meds)
        meds = meds[: a.n]
    for sub in ("box", "pill"):
        (a.out / sub).mkdir(parents=True, exist_ok=True)

    proc = Sam3Processor(build_sam3_image_model())
    torch.autocast("cuda", dtype=torch.bfloat16).__enter__()  # SAM 3 mixes bf16 and fp32 without it
    stats = {"medicines": len(meds), "box_ok": 0, "pill_medicines_ok": 0, "pills": 0}
    boxes: list[Path] = []
    pills: list[Path] = []
    t0 = time.time()
    with (a.out / "index.jsonl").open("w", encoding="utf-8") as index, (a.out / "rejected.jsonl").open("w", encoding="utf-8") as rejected:
        for n, med in enumerate(meds, 1):
            nr = med["nregistro"]
            row = {"nregistro": nr, "nombre": med["nombre"], "pactivos": med["pactivos"], "forma": med["forma"],
                   "oral_solid": bool(ORAL_SOLID.search(med["forma"] or "")), "boxes": [], "pills": []}
            for photo, sub, cutter in (("materialas", "box", cut_box), ("formafarmac", "pill", cut_pills)):
                cuts, reason = cutter(proc, load_photo(a.cima / "images" / "full" / photo / f"{nr}.jpg"))
                for k, rgba in enumerate(cuts):
                    path = a.out / sub / f"{nr}_{k}.png"
                    cv2.imwrite(str(path), rgba)
                    row["boxes" if sub == "box" else "pills"].append(path.name)
                    (boxes if sub == "box" else pills).append(path)
                if reason:
                    rejected.write(json.dumps({"nregistro": nr, "photo": photo, "reason": reason}) + "\n")
            stats["box_ok"] += bool(row["boxes"])
            stats["pill_medicines_ok"] += bool(row["pills"])
            stats["pills"] += len(row["pills"])
            index.write(json.dumps(row, ensure_ascii=False) + "\n")
            if n % 100 == 0:
                print(f"{n}/{len(meds)}  {(time.time() - t0) / n:.2f} s per medicine", flush=True)
    contact_sheet(boxes[:100], a.out / "contact_sheet_box.jpg")
    contact_sheet(pills[:100], a.out / "contact_sheet_pill.jpg")
    print(json.dumps(stats), f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
