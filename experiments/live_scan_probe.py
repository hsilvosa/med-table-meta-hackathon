"""Feasibility of a LIVE scan: recall and time per frame if the preview frames are smaller than the full photo, by camera distance.

  .venv-app/Scripts/python.exe experiments/live_scan_probe.py
Frames are the saved 12 MP room photos downscaled to a width (the size a live preview would be analysed at).
"""

import glob
import json
import sys
import time
from collections import defaultdict

import cv2

sys.path.insert(0, "src")
from medtable import decode  # noqa: E402

FAST = ((3.0, "strong"),)
MEDIUM = ((2.0, "soft"), (3.0, "strong"))
FULL = decode.ZOOM_PASSES
files = [p for p in sorted(glob.glob("data/world_photos_batch70/photo_*.json")) + sorted(glob.glob("data/world_photos_90cm_fresh/photo_*.json"))]
chosen = files[:: max(1, len(files) // 30)][:30]

stats = defaultdict(lambda: [0, 0, 0.0, 0])      # (width, passes, band) -> hits, total, seconds, frames
for p in chosen:
    truth = json.load(open(p))
    full = cv2.imread(p.replace(".json", ".jpg"), cv2.IMREAD_GRAYSCALE)
    d = truth["distance_m"]
    band = "<0.5 m" if d < 0.5 else "0.5-0.75 m" if d < 0.75 else "0.75-1.0 m"
    for width in (4000, 2000, 1333):
        gray = full if width == 4000 else cv2.resize(full, None, fx=width / 4000, fy=width / 4000, interpolation=cv2.INTER_AREA)
        for name, passes in (("fast", FAST), ("medium", MEDIUM), ("full", FULL)):
            t0 = time.time()
            texts = {x.text for x in decode._zxing(gray, 1.0, (0, 0), "plain")} | {x.text for x in decode.find_zoomed(gray, passes)}
            dt = time.time() - t0
            s = stats[(width, name, band)]
            for label in truth["labels"]:
                s[0] += label["text"] in texts
                s[1] += 1
            s[2] += dt
            s[3] += 1
print(f"{len(chosen)} photos")
for key in sorted(stats):
    hits, total, seconds, frames = stats[key]
    print(f"width {key[0]:4} passes {key[1]:6} {key[2]:11} recall {hits:3}/{total:3} = {100 * hits / max(total, 1):5.1f}%   {seconds / frames:.2f} s per frame")
