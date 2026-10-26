"""Render GS1 Data Matrix label textures for the Blender scenes (needs the app environment: zxing-cpp, OpenCV).

  .venv-app/Scripts/python.exe scripts/make_label_textures.py OUT_DIR [--count 40] [--seed 1]

Writes OUT_DIR/label_000.png ... and OUT_DIR/labels.json {file: element string}. Each code is a Spanish-style NTIN
(CN 848226) with its own serial number, 16 pixels per module with a 4-module quiet zone.
"""

import argparse
import json
import random
import sys
from pathlib import Path

import cv2

sys.path.insert(0, "src")
from medtable.synthetic import ntin_element_string, render_datamatrix  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out_dir", type=Path)
ap.add_argument("--count", type=int, default=40)
ap.add_argument("--seed", type=int, default=1)
args = ap.parse_args()
args.out_dir.mkdir(parents=True, exist_ok=True)
rng = random.Random(args.seed)
labels = {}
for i in range(args.count):
    text = ntin_element_string("848226", lot=f"L{i:03d}", serial=f"SN{rng.randrange(10**6):06d}")
    name = f"label_{i:03d}.png"
    cv2.imwrite(str(args.out_dir / name), render_datamatrix(text, module_px=16, quiet=4))
    labels[name] = text
(args.out_dir / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
print(f"{len(labels)} labels in {args.out_dir}")
