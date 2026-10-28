"""How small and how blurred can a pack's Data Matrix be and still decode?

  .venv-app/Scripts/python.exe experiments/decode_robustness.py [--trials 4] [--canvas 2400x1800]

Renders real GS1 Data Matrix codes (zxing-cpp writer) with a given number of pixels per module, rotates and tilts
them a little, blurs the whole photo, adds sensor noise and pastes the code at a random place on a plain table.
Reports the share decoded (a) from the whole image only and (b) with the tiled/upscaled search of `decode.py`.

These are perfect printed codes: real packs add glare, curved cardboard and print defects, so read the rates as an
upper bound. The point is the minimum pixels per module, which tells how close the camera has to be.
Reference: a pack code is about 1 cm for 22-26 modules, so one module is about 0.4 mm; a 12 MP phone photo
(4000 px) of a table 60 cm wide gives about 2.7 px per module, a close-up of a 20 cm field about 8.
"""

import argparse
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "tests")
from helpers import ntin_element_string, render_datamatrix  # noqa: E402
from medtable import decode  # noqa: E402


def make_photo(canvas: tuple[int, int], module_px: float, blur: float, rng: random.Random) -> tuple[np.ndarray, str]:
    w, h = canvas
    text = ntin_element_string("848226", serial=f"SN{rng.randrange(10**6):06d}")
    scale = max(module_px, 1.0)
    code = render_datamatrix(text, module_px=1)  # one pixel per module (+ quiet zone), enlarged below with the true factor
    side = int(round(code.shape[0] * scale))
    code = cv2.resize(code, (side, side), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST)
    photo = np.full((h, w, 3), rng.randint(150, 215), np.uint8)
    photo = np.clip(photo + np.random.default_rng(rng.randrange(1 << 30)).normal(0, 3, photo.shape), 0, 255).astype(np.uint8)
    x, y = rng.randint(side, w - 2 * side), rng.randint(side, h - 2 * side)
    photo[y:y + side, x:x + side] = code
    angle = rng.choice([0, rng.uniform(-45, 45), 90])
    photo = cv2.warpAffine(photo, cv2.getRotationMatrix2D((x + side / 2, y + side / 2), angle, 1.0), (w, h), borderValue=(180, 180, 180))
    tilt = np.float32([[rng.uniform(-0.02, 0.02) * w, rng.uniform(-0.02, 0.02) * h] for _ in range(4)])
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    photo = cv2.warpPerspective(photo, cv2.getPerspectiveTransform(corners, corners + tilt), (w, h), borderValue=(180, 180, 180))
    if blur:
        photo = cv2.GaussianBlur(photo, (0, 0), blur)
    noisy = photo + np.random.default_rng(rng.randrange(1 << 30)).normal(0, 4, photo.shape)
    return np.clip(noisy, 0, 255).astype(np.uint8), text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--canvas", default="2400x1800")
    ap.add_argument("--out", type=Path, default=Path("experiments/out/decode_robustness.txt"))
    args = ap.parse_args()
    canvas = tuple(int(v) for v in args.canvas.split("x"))
    rng = random.Random(0)
    modules = [2, 3, 4, 5, 6, 8]
    blurs = [0.0, 1.0, 2.0]
    lines = [f"canvas {args.canvas}, {args.trials} trials per cell; each cell: whole-image decode / tiled decode (share of codes read exactly)",
             "px/module | " + " | ".join(f"blur {b:g}" for b in blurs)]
    timing = {"full": 0.0, "tiles": 0.0}
    count = 0
    for m in modules:
        row = []
        for b in blurs:
            ok_full = ok_tiles = 0
            for _ in range(args.trials):
                photo, text = make_photo(canvas, m, b, rng)
                t = time.time()
                ok_full += any(d.text == text for d in decode.find_datamatrix(photo, tiles=False))
                timing["full"] += time.time() - t
                t = time.time()
                ok_tiles += any(d.text == text for d in decode.find_datamatrix(photo, tiles=True))
                timing["tiles"] += time.time() - t
                count += 1
            row.append(f"{ok_full}/{args.trials} / {ok_tiles}/{args.trials}")
        lines.append(f"{m:>9} | " + " | ".join(row))
        print(lines[-1], flush=True)
    lines.append(f"mean decode time: whole image {timing['full'] / count:.2f} s, tiled {timing['tiles'] / count:.2f} s")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
