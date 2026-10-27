"""Evaluate the pipeline on the photos taken in the 3D room (data/world_photos/photo_*.jpg + .json ground truth).

  .venv-app/Scripts/python.exe experiments/eval_world.py [DIR=data/world_photos] [--since 20261027_09]

For every photo: the codes that were in view (from the room's own truth) against what `identify.identify` read.
Outcomes per code in view: verified_correct, unverified_as_expected (the deliberately unknown CN), missed, and for the whole
photo verified_wrong (a pack verified that is not in the truth: the headline safety number). Also the expiry flag against the
case built into the scene and the decode rate by pixels-per-module.
Caveat: the room is a stage set (flat cut-outs with generated stickers), so this is an upper bound for real photos.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, "src")
sys.path.insert(0, "experiments")
from eval_photos import clopper_pearson  # noqa: E402
from medtable import identify  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("folder", nargs="?", type=Path, default=Path("data/world_photos"))
ap.add_argument("--since", default="", help="only photos whose name starts with photo_<prefix>")
args = ap.parse_args()
resolver = Resolver("data/cache/cima")
c = Counter()
bins: dict[str, list[int]] = {}
dist_bins: dict[str, list[int]] = {}
problems = []
photos = sorted(p for p in args.folder.glob(f"photo_{args.since}*.jpg"))
for photo in photos:
    truth = json.loads(photo.with_suffix(".json").read_text(encoding="utf-8"))
    readings = identify.identify(cv2.imread(str(photo)), resolver)
    by_cn = {r.cn: r for r in readings if r.cn}
    seen_truth = set()
    for label in truth["labels"]:
        seen_truth.add(label["cn7"])
        r = by_cn.get(label["cn7"])
        ppm = label["px_per_module"]
        bucket = "<2" if ppm < 2 else "2-3" if ppm < 3 else "3-4" if ppm < 4 else "4-6" if ppm < 6 else "6+"
        ok = False
        if label["case"] == "unknown_cn":
            ok = bool(r and r.status == "unverified")
            c["unverified_as_expected" if ok else "missed"] += 1
        elif r and r.status == "verified":
            c["verified_correct"] += 1
            ok = True
            if (label["case"] == "expired") != bool(r.expired):
                c["expiry_flag_wrong"] += 1
                problems.append(f"{photo.name}: expiry flag wrong for {label['name'][:30]} (case {label['case']}, expired {r.expired})")
        else:
            c["missed"] += 1
            problems.append(f"{photo.name}: missed {label['name'][:30]} at {label['px_per_module']} px/module")
        bins.setdefault(bucket, []).append(int(ok))
        d = truth["distance_m"]
        dist_bins.setdefault("<0.4 m" if d < 0.4 else "0.4-0.5" if d < 0.5 else "0.5-0.6" if d < 0.6 else "0.6-0.75" if d < 0.75 else "0.75+", []).append(int(ok))
    for r in readings:
        if r.status == "verified" and r.cn not in seen_truth:
            c["verified_wrong"] += 1
            problems.append(f"{photo.name}: VERIFIED WRONG {r.cn} {r.medicine.name if r.medicine else ''}")
    c["no_code_boxes"] += len(truth["boxes_without_code"])

total = c["verified_correct"] + c["unverified_as_expected"] + c["missed"]
print(f"photos {len(photos)}; codes in view {total}; boxes without a code in view {c['no_code_boxes']}")
for key in ("verified_correct", "unverified_as_expected", "missed"):
    lo, hi = clopper_pearson(c[key], total)
    print(f"  {key:24} {c[key]:>3}/{total}  {c[key] / max(total, 1):6.1%}  95% CI [{lo:.1%}, {hi:.1%}]")
verified = c["verified_correct"] + c["verified_wrong"]
print(f"  CONFIDENT-WRONG: {c['verified_wrong']} of {verified} verified; 95% CI upper bound {clopper_pearson(c['verified_wrong'], verified)[1]:.1%}")
print(f"  expiry flag wrong: {c['expiry_flag_wrong']}")
for name in ("<2", "2-3", "3-4", "4-6", "6+"):
    if name in bins:
        print(f"  px/module {name:>3}: read {sum(bins[name]):>3}/{len(bins[name]):<3} {sum(bins[name]) / len(bins[name]):5.0%}")
for name in ("<0.4 m", "0.4-0.5", "0.5-0.6", "0.6-0.75", "0.75+"):
    if name in dist_bins:
        print(f"  camera {name:>9} above the table: read {sum(dist_bins[name]):>3}/{len(dist_bins[name]):<3} {sum(dist_bins[name]) / len(dist_bins[name]):5.0%}")
for line in problems[:20]:
    print("   ", line)
