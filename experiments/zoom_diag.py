"""Why do some codes survive the zoomed scan? Take the codes the scan misses (truth known) and try window sizes, scales and sharpening around them.

  .venv-app/Scripts/python.exe experiments/zoom_diag.py data/world_photos_90cm
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "src")
from medtable import decode  # noqa: E402

folder = Path(sys.argv[1])
only = sys.argv[2].split(",") if len(sys.argv) > 2 else []   # photo name tails to restrict to
missed = []
for photo in sorted(folder.glob("photo_*.jpg")):
    truth = json.loads(photo.with_suffix(".json").read_text(encoding="utf-8"))
    gray = cv2.imread(str(photo), cv2.IMREAD_GRAYSCALE)
    if only and not any(photo.stem.endswith(o) for o in only):
        continue
    found = {d.text for d in decode.find_datamatrix(gray, libdmtx=False)}
    missed += [(photo, gray, label) for label in truth["labels"] if label["text"] not in found and label["case"] != "unknown_cn"]
print("missed by the current scan:", len(missed))

hits: dict[str, int] = defaultdict(int)
for photo, gray, label in missed:
    cx, cy = label["px"]
    for tile in (240, 640):
        x0, y0 = max(cx - tile // 2, 0), max(cy - tile // 2, 0)
        window = gray[y0:y0 + tile, x0:x0 + tile]
        for scale in (2.0, 3.0, 4.0, 5.0, 6.0):
            up = cv2.resize(window, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            variants = {"plain": up,
                        "unsharp": cv2.addWeighted(up, 2.2, cv2.GaussianBlur(up, (0, 0), 0.6 * scale), -1.2, 0),
                        "strong": cv2.addWeighted(up, 3.0, cv2.GaussianBlur(up, (0, 0), 0.9 * scale), -2.0, 0),
                        "stronger": cv2.addWeighted(up, 4.0, cv2.GaussianBlur(up, (0, 0), 1.2 * scale), -3.0, 0),
                        "strong_wide": cv2.addWeighted(up, 2.6, cv2.GaussianBlur(up, (0, 0), 1.5 * scale), -1.6, 0),
                        "adapt_big": cv2.adaptiveThreshold(cv2.addWeighted(up, 3.0, cv2.GaussianBlur(up, (0, 0), 0.9 * scale), -2.0, 0), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, int(scale * 12) | 1, 4),
                        "clahe": cv2.createCLAHE(3.0, (4, 4)).apply(up),
                        "adapt": cv2.adaptiveThreshold(up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, int(scale * 8) | 1, 5)}
            for name, img in variants.items():
                texts = {d.text for d in decode._zxing(img, scale, (x0, y0), "diag")}
                if label["text"] in texts:
                    hits[f"tile{tile}/x{scale:g}/{name}"] += 1
            # libdmtx on the enlarged window
            try:
                from pylibdmtx import pylibdmtx
                got = [r.data.decode("utf-8", "replace") for r in pylibdmtx.decode(variants["unsharp"], timeout=300, max_count=1)]
                if label["text"] in got:
                    hits[f"tile{tile}/x{scale:g}/libdmtx"] += 1
            except Exception:   # noqa: BLE001
                pass
print("successes per configuration (out of", len(missed), "missed codes):")
for k, v in sorted(hits.items(), key=lambda kv: -kv[1])[:16]:
    print(f"  {k:28} {v}")
print("never read by any configuration:", sum(1 for photo, gray, label in missed
      if not any(True for _ in [])) if False else "")
