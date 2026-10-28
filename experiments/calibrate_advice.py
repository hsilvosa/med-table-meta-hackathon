"""How the numbers of medtable.advice were found, and a check that they still hold.

  .venv-app/Scripts/python.exe experiments/calibrate_advice.py [--photos 14]

1. MODULE_PER_PACK_SIDE: for each code in the ground truth of the room photos that lies inside a pack found by medtable.boxes, the ratio between the pixels
   per module of the code (known from the room) and the side of the pack (square with the same area). The median is the constant.
2. The light and sharpness measures of medtable.advice.frame_quality on the same photos made dark, washed out, over-exposed, noisy, shaken and out of focus
   (the degradations of eval_conditions.py), to see where the thresholds fall between "fine" and "needs advice".
"""

import argparse
import glob
import json
import statistics
import sys

import cv2
import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "experiments")
from eval_conditions import CONDITIONS, pick  # noqa: E402
from medtable import advice, boxes  # noqa: E402


def main(n):
    ratios, quality = [], {}
    for path in pick(n):
        truth = json.load(open(path.replace(".jpg", ".json")))
        img = cv2.imread(path)
        for pack in boxes.find_packs(img):
            x0, y0, x1, y1 = pack["bbox"]
            for label in truth["labels"]:
                if x0 <= label["px"][0] <= x1 and y0 <= label["px"][1] <= y1:
                    ratios.append(label["px_per_module"] / pack["side"])
        for name in ("clear", "dark", "very_dark", "washed_out", "overexposed", "noisy", "shake", "defocus", "jpeg_q25"):
            gray = cv2.cvtColor(CONDITIONS[name](img), cv2.COLOR_BGR2GRAY)
            quality.setdefault(name, []).append(advice.frame_quality(gray))
    print(f"pixels per module / pack side: n={len(ratios)} median={statistics.median(ratios):.4f} 10%={np.percentile(ratios, 10):.4f} 90%={np.percentile(ratios, 90):.4f}")
    for name, rows in quality.items():
        print(f"{name:12}", "  ".join(f"{key} {min(r[key] for r in rows):7.3f}..{max(r[key] for r in rows):7.3f}" for key in ("mean", "burnt", "blur_ratio")))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", type=int, default=14)
    main(ap.parse_args().photos)
