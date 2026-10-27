"""How far can a single image be pushed? For every code in view in the room photos (truth known) try decoding a crop around it
with different upscaling / sharpening / thresholding, per camera-distance bin. Tells whether the limit is the decoder or the pixels.

  .venv-app/Scripts/python.exe experiments/lowres_probe.py [DIR=data/world_photos] [--min-dist 0.7]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "src")
import zxingcpp  # noqa: E402
from pylibdmtx import pylibdmtx  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("folder", nargs="?", type=Path, default=Path("data/world_photos"))
ap.add_argument("--min-dist", type=float, default=0.7)
ap.add_argument("--limit", type=int, default=40, help="codes to try (spread evenly)")
args = ap.parse_args()


def zx(img) -> list[str]:
    return [r.text for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.DataMatrix, try_rotate=True, try_downscale=True, try_invert=True)]


def dm(img) -> list[str]:
    return [r.data.decode("utf-8", "replace") for r in pylibdmtx.decode(img, timeout=250, max_count=1, shrink=1)]


def variants(crop_gray: np.ndarray):
    yield "raw", crop_gray
    for f in (2, 3, 4):
        for name, interp in (("cubic", cv2.INTER_CUBIC), ("lanczos", cv2.INTER_LANCZOS4)):
            up = cv2.resize(crop_gray, None, fx=f, fy=f, interpolation=interp)
            yield f"{name}x{f}", up
            blur = cv2.GaussianBlur(up, (0, 0), 1.2 * f / 2)
            yield f"{name}x{f}+unsharp", cv2.addWeighted(up, 2.2, blur, -1.2, 0)
            yield f"{name}x{f}+otsu", cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            yield f"{name}x{f}+adapt", cv2.adaptiveThreshold(up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 2 * int(f * 6) + 1, 6)


todo = []
for photo in sorted(args.folder.glob("photo_*.jpg")):
    truth = json.loads(photo.with_suffix(".json").read_text(encoding="utf-8"))
    if truth["distance_m"] >= args.min_dist:
        todo += [(photo, label) for label in truth["labels"]]
todo = todo[:: max(1, len(todo) // args.limit)][: args.limit]
hits: dict[str, int] = defaultdict(int)
total = 0
by_bin: dict[str, list[int]] = defaultdict(lambda: [0, 0])
cache: dict[Path, np.ndarray] = {}
for photo, label in todo:
    if True:
        gray = cache.setdefault(photo, cv2.imread(str(photo), cv2.IMREAD_GRAYSCALE))
        cx, cy = label["px"]
        half = int(14 * label["px_per_module"] * 1.7) + 8
        crop = gray[max(cy - half, 0):cy + half, max(cx - half, 0):cx + half]
        total += 1
        ok_any = False
        for name, img in variants(crop):
            for decoder, fn in (("zx", zx), ("dm", dm)):
                try:
                    texts = fn(img)
                except Exception:   # noqa: BLE001
                    texts = []
                if any(label["text"][:30] in t or t[:30] in label["text"] for t in texts):
                    hits[f"{name}/{decoder}"] += 1
                    ok_any = True
        b = f"{label['px_per_module']:.1f}"
        by_bin[f"{int(label['px_per_module'] * 4) / 4:.2f}"][0] += ok_any
        by_bin[f"{int(label['px_per_module'] * 4) / 4:.2f}"][1] += 1
print("codes tried:", total)
for k, v in sorted(hits.items(), key=lambda kv: -kv[1])[:14]:
    print(f"  {k:28} {v}/{total}")
print("any variant, by px/module bin:")
for k in sorted(by_bin):
    print(f"  {k}: {by_bin[k][0]}/{by_bin[k][1]}")
