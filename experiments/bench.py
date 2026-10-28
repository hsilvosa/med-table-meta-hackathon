"""Benchmark of the reading path, to compare before and after a change: speed and recall on a fixed set of room photos.

  .venv-app/Scripts/python.exe experiments/bench.py [--out result.json] [--photos 24]

- full read: identify.identify (what the planner does with a photo)
- live scan: live_scan.scan up to its last stage (what the preview does with a frame), and the time of its first stage that holds a code
- recall: share of the codes in the ground truth of each photo (labels in the .json next to it) that were read
The photos: the 90 cm batch and the 0.5-0.95 m batch of the room (data/world_photos_90cm_fresh, data/world_photos_boxes_heldout), taken in turns.
"""

import argparse
import glob
import json
import os
import statistics
import sys
import time

import cv2

sys.path.insert(0, "src")
t0 = time.perf_counter()
from medtable import identify, live_scan  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402

IMPORT_SECONDS = time.perf_counter() - t0
FOLDERS = ("data/world_photos_90cm_fresh", "data/world_photos_boxes_heldout")


def pick(n):
    lists = [sorted(glob.glob(f"{folder}/photo_*.jpg")) for folder in FOLDERS]
    out = []
    for i in range(n):
        source = lists[i % len(lists)]
        out.append(source[(i // len(lists)) * max(1, len(source) // (n // len(lists) + 1)) % len(source)])
    return list(dict.fromkeys(out))


def main(n, out):
    resolver = Resolver("data/cache/cima")
    photos = pick(n)
    rows = []
    for path in photos:
        truth = {label["text"] for label in json.load(open(path.replace(".jpg", ".json")))["labels"]}
        image = cv2.imread(path)
        with open(path, "rb") as fh:
            jpeg = fh.read()
        t = time.perf_counter()
        readings = identify.identify(image, resolver)
        full = time.perf_counter() - t
        full_hits = len({r.raw for r in readings} & truth)
        t = time.perf_counter()
        first, live_hits, stages = None, 0, 0
        for stage in live_scan.scan(jpeg):
            stages += 1
            if first is None and stage["codes"]:
                first = time.perf_counter() - t
            last = stage
        live = time.perf_counter() - t
        rows.append(dict(photo=os.path.basename(path), codes=len(truth), full_s=full, full_hits=full_hits, live_s=live, live_first_s=first,
                         live_found=len(last["codes"]), nocode=len(last["nocode"])))
    total = sum(r["codes"] for r in rows)
    summary = dict(
        photos=len(rows), codes=total,
        import_s=round(IMPORT_SECONDS, 2),
        full_mean_s=round(statistics.mean(r["full_s"] for r in rows), 3), full_median_s=round(statistics.median(r["full_s"] for r in rows), 3),
        full_recall=round(sum(r["full_hits"] for r in rows) / total, 4),
        live_mean_s=round(statistics.mean(r["live_s"] for r in rows), 3), live_median_s=round(statistics.median(r["live_s"] for r in rows), 3),
        live_first_mean_s=round(statistics.mean(r["live_first_s"] for r in rows if r["live_first_s"] is not None), 3),
        live_found_mean=round(statistics.mean(r["live_found"] for r in rows), 2),
    )
    print(json.dumps(summary, indent=1))
    if out:
        json.dump(dict(summary=summary, rows=rows), open(out, "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--photos", type=int, default=24)
    args = ap.parse_args()
    main(args.photos, args.out)
