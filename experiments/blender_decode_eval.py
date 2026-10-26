"""Decode rate on Blender-rendered table scenes as a function of camera height (phone-like 12 MP photo).

  .venv-app/Scripts/python.exe experiments/blender_decode_eval.py [--scenes 6] [--heights 0.25,0.35,0.5,0.7,0.9] [--glossy 0.25]

Needs Blender 4.5 (path below). Generates label textures (square Data Matrix, scripts/make_label_textures.py), renders
`--scenes` scenes per height with scripts/blender_scene.py (boxes with a 12 mm code on top, random pose, tilt up to 20 degrees,
one area light, glossy surfaces) and decodes every scene with decode.find_datamatrix. Prints, per height, the share of codes
read exactly, the median pixels per module of the codes that were found, and the mean decode time.
Perfect rendered labels and no cardboard curvature, print defects or motion blur: an upper bound for real packs.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, "src")
from medtable import decode  # noqa: E402

BLENDER = "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"
ap = argparse.ArgumentParser()
ap.add_argument("--scenes", type=int, default=6)
ap.add_argument("--heights", default="0.25,0.35,0.5,0.7,0.9")
ap.add_argument("--glossy", default="0.25")
ap.add_argument("--root", type=Path, default=Path("data/blender"))
args = ap.parse_args()

labels = args.root / "labels"
if not (labels / "labels.json").exists():
    subprocess.run([sys.executable, "scripts/make_label_textures.py", str(labels), "--count", "40"], check=True)
lines = [f"{args.scenes} scenes per height, 4000x3000, glossy {args.glossy}; share of codes read exactly (zxing, then tiles), median px/module of codes found",
         "camera height | codes | whole-image | with tiles | px/module | decode time (tiled)"]
for height in args.heights.split(","):
    out = args.root / f"h{height}"
    subprocess.run([BLENDER, "--background", "--python", "scripts/blender_scene.py", "--", str(out), str(labels), "--scenes", str(args.scenes),
                    "--camera-height", height, "--seed", "7", "--glossy", args.glossy], check=True, capture_output=True)
    truth = json.loads((out / "truth.json").read_text(encoding="utf-8"))
    total = whole = tiled = 0
    sizes, seconds = [], []
    for scene, texts in truth.items():
        img = cv2.imread(str(out / scene))
        total += len(texts)
        whole += len({d.text for d in decode.find_datamatrix(img, tiles=False, libdmtx=False)} & set(texts))
        start = time.time()
        found = decode.find_datamatrix(img, tiles=True, libdmtx=True)
        seconds.append(time.time() - start)
        tiled += len({d.text for d in found} & set(texts))
        sizes += [max(d.bbox[2] - d.bbox[0], d.bbox[3] - d.bbox[1]) / 24 for d in found if d.text in texts]  # about 24 modules per side
    lines.append(f"{height:>13} m | {total:>5} | {whole:>3}/{total} {whole / total:>4.0%} | {tiled:>3}/{total} {tiled / total:>4.0%} | "
                 f"{statistics.median(sizes) if sizes else float('nan'):>9.1f} | {statistics.mean(seconds):.2f} s")
    print(lines[-1], flush=True)
report = args.root / "decode_by_height.txt"
report.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
