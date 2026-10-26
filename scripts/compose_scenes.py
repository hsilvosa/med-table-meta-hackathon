"""Compose synthetic desk scenes from the cut-outs, with ground-truth labels.

  python scripts/compose_scenes.py [--n 12 --seed 1] [--cutouts data/cutouts] [--out data/scenes]

Each scene is a procedural surface (laminate, cloth or soft wood) with 4-9 packs and 2-6 loose pills pasted
in random order with rotation, a small perspective tilt, soft contact shadows, per-object light change and
camera noise. Scale follows real size: a pack is about 14 cm long, a pill 0.9-1.8 cm. Objects stay inside the
frame; they can overlap. annotations.json stores, per object, the CIMA nregistro, name, kind and the VISIBLE
polygon after occlusion (objects with under 30% visible are dropped).

Synthetic scenes are for developing and stress-testing only; accuracy claims must come from real photos.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

W, H = 1280, 960
PACK_CM = 14.0


def surface(rng: random.Random) -> np.ndarray:
    nrng = np.random.default_rng(rng.randrange(1 << 30))
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)

    def smooth_noise(cells_h: int, cells_w: int) -> np.ndarray:
        return cv2.resize(nrng.normal(size=(cells_h, cells_w)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)

    kind = rng.choice(["laminate", "cloth", "wood"])
    if kind == "laminate":
        base = np.array(rng.choice([(226, 226, 222), (200, 205, 205), (165, 170, 172), (60, 62, 66)]), np.float32)
        img = base * (1 + smooth_noise(H // 4, W // 4)[..., None] * 0.015)
    elif kind == "cloth":
        base = np.array(rng.choice([(200, 215, 230), (150, 170, 200), (205, 190, 172), (232, 232, 232)]), np.float32)
        weave = np.sin(x * 1.3) * np.sin(y * 1.3) * 0.035
        img = base * (1 + weave[..., None] + smooth_noise(H // 3, W // 3)[..., None] * 0.02)
    else:  # wood, kept low contrast so it does not dominate the scene
        base = np.array(rng.choice([(95, 130, 175), (75, 105, 150), (125, 160, 200)]), np.float32)
        grain = np.sin((x + smooth_noise(12, 16) * 22) / rng.uniform(6, 10)) * 0.5 + 0.5
        img = base * (0.9 + 0.12 * grain[..., None] + smooth_noise(H // 2, W // 2)[..., None] * 0.04)
    cx, cy = rng.uniform(0, W), rng.uniform(-200, H * 0.5)  # soft window light
    falloff = 1.12 - 0.40 * np.clip(np.hypot(x - cx, y - cy) / np.hypot(W, H), 0, 1)
    return np.clip(img * falloff[..., None], 0, 255).astype(np.float32)


def make_sprite(path: Path, longest_px: float, rng: random.Random):
    """Load a cut-out, tilt it slightly in perspective, rotate it and return (bgr float, alpha float)."""
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if rng.random() < 0.15:
        im = im[:, ::-1]
    s = longest_px / max(im.shape[:2])
    im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    h, w = im.shape[:2]
    pad = int(0.25 * max(h, w))
    canvas = cv2.copyMakeBorder(im, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    ch, cw = canvas.shape[:2]
    j = lambda: rng.uniform(-0.05, 0.05)  # noqa: E731 - perspective jitter, fraction of the size
    src = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
    dst = src + np.float32([[j() * cw, j() * ch] for _ in range(4)])
    canvas = cv2.warpPerspective(canvas, cv2.getPerspectiveTransform(src, dst), (cw, ch))
    angle = rng.uniform(0, 360) if min(h, w) / max(h, w) > 0.6 else rng.choice([rng.uniform(-35, 35), rng.uniform(55, 125)])
    diag = int(np.hypot(ch, cw)) + 4
    big = cv2.copyMakeBorder(canvas, (diag - ch) // 2, diag - ch - (diag - ch) // 2, (diag - cw) // 2, diag - cw - (diag - cw) // 2,
                             cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    rot = cv2.warpAffine(big, cv2.getRotationMatrix2D((diag / 2, diag / 2), angle, 1.0), (diag, diag))
    ys, xs = np.where(rot[..., 3] > 8)
    rot = rot[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return rot[..., :3].astype(np.float32) * rng.uniform(0.9, 1.07), rot[..., 3].astype(np.float32) / 255.0


def paste(canvas: np.ndarray, sprite: np.ndarray, alpha: np.ndarray, x: int, y: int, shadow: tuple[int, int, float]) -> np.ndarray:
    """Blend a sprite onto the canvas with a soft offset shadow; return its full-frame alpha."""
    h, w = alpha.shape
    dx, dy, strength = shadow
    layer = np.zeros((H, W), np.float32)
    layer[y:y + h, x:x + w] = alpha
    shade = cv2.GaussianBlur(np.roll(layer, (dy, dx), axis=(0, 1)), (0, 0), 8) * strength
    canvas *= (1 - shade)[..., None]
    region = canvas[y:y + h, x:x + w]
    canvas[y:y + h, x:x + w] = region * (1 - alpha[..., None]) + sprite * alpha[..., None]
    return layer


def compose(rng: random.Random, index: list[dict], cutouts: Path):
    canvas = surface(rng)
    shadow = (rng.randint(5, 14), rng.randint(7, 16), rng.uniform(0.35, 0.6))
    px_per_cm = rng.uniform(21, 28)
    jobs = [("box", m, rng.choice(m["boxes"])) for m in rng.sample(index, rng.randint(4, 9))]
    oral = [m for m in index if m["oral_solid"] and m["pills"]]
    jobs += [("pill", m, rng.choice(m["pills"])) for m in rng.sample(oral, min(len(oral), rng.randint(2, 6)))]
    rng.shuffle(jobs)

    layers: list[tuple[np.ndarray, dict]] = []
    for kind, med, fname in jobs:
        longest = PACK_CM * px_per_cm * rng.uniform(0.85, 1.15) if kind == "box" else px_per_cm * rng.uniform(0.9, 1.8)
        sprite, alpha = make_sprite(cutouts / kind / fname, longest, rng)
        h, w = alpha.shape
        if h >= H or w >= W:
            continue
        x, y = rng.randint(0, W - w), rng.randint(0, H - h)
        layer = paste(canvas, sprite, alpha, x, y, shadow)
        layers.append((layer > 0.5, {"kind": kind, "nregistro": med["nregistro"], "nombre": med["nombre"], "file": fname}))

    annotations, covered = [], np.zeros((H, W), bool)
    for mask, meta in reversed(layers):  # later pastes hide earlier ones
        visible = mask & ~covered
        covered |= mask
        frac = visible.sum() / max(mask.sum(), 1)
        if frac < 0.3 or visible.sum() < 150:
            continue
        contour = max(cv2.findContours(visible.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
        annotations.append({**meta, "visible_frac": round(float(frac), 3), "bbox": list(cv2.boundingRect(contour)),
                            "polygon": cv2.approxPolyDP(contour, 2.0, True).reshape(-1, 2).tolist()})

    img = cv2.GaussianBlur(canvas * rng.uniform(0.92, 1.05), (0, 0), rng.uniform(0.3, 0.9))
    img += np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(1.5, 4.0), img.shape)
    return np.clip(img, 0, 255).astype(np.uint8), annotations


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cutouts", type=Path, default=Path("data/cutouts"))
    ap.add_argument("--out", type=Path, default=Path("data/scenes"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    index = [json.loads(line) for line in (a.cutouts / "index.jsonl").open(encoding="utf-8")]
    index = [m for m in index if m["boxes"]]
    rng = random.Random(a.seed)

    all_annotations, previews = {}, []
    for i in range(a.n):
        img, anns = compose(rng, index, a.cutouts)
        name = f"scene_{i:04d}.jpg"
        cv2.imwrite(str(a.out / name), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        all_annotations[name] = anns
        if i < 6:
            shown = img.copy()
            for an in anns:
                colour = (0, 255, 0) if an["kind"] == "box" else (0, 0, 255)
                cv2.polylines(shown, [np.array(an["polygon"], np.int32)], True, colour, 3)
            previews.append(cv2.resize(shown if i % 2 == 0 else img, (640, 480)))
    json.dump(all_annotations, (a.out / "annotations.json").open("w", encoding="utf-8"), ensure_ascii=False)
    if len(previews) >= 6:
        cv2.imwrite(str(a.out / "preview.jpg"), np.vstack([np.hstack(previews[:3]), np.hstack(previews[3:6])]))
    print(sum(len(v) for v in all_annotations.values()), "labelled objects in", a.n, "scenes ->", a.out)


if __name__ == "__main__":
    main()
