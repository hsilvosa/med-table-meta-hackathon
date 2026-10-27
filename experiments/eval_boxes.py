"""How well does the light box finder (medtable.boxes) work on the 3D-room photos?

  .venv-app/Scripts/python.exe experiments/eval_boxes.py data/world_photos_boxes [--show N]

Ground truth is in each photo's .json ("boxes": where every pack is, how much of it is visible, whether its sticker is visible), written by web/main.js.
Only packs entirely in the frame and at least 75 % visible are counted ("clear" packs). The codes are read with the same fast scan as the live preview
(decode.LIVE_PASSES); the result is cached in live_codes.json inside the folder.
"""

import glob
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, "src")
from medtable import boxes as boxfinder  # noqa: E402
from medtable import decode  # noqa: E402


def iou(a, b):
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def contains_centre(box, code):
    return box[0] <= (code[0] + code[2]) / 2 <= box[2] and box[1] <= (code[1] + code[3]) / 2 <= box[3]


def main(folder: str, show: int) -> None:
    folder_path = Path(folder)
    cache_path = folder_path / "live_codes.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    photos = sorted(glob.glob(str(folder_path / "photo_*.jpg")))
    stats = dict(photos=0, clear=0, found=0, no_code_clear=0, no_code_flagged=0, flagged=0, flagged_true=0, flagged_nonbox=0, flagged_has_code_box=0,
                 sticker_absent=0, sticker_absent_flagged=0, sticker_unread=0, sticker_unread_flagged=0, regions=0, regions_nonbox=0)
    nonbox_examples = []
    for path in photos:
        truth = json.loads(Path(path).with_suffix(".json").read_text())
        if "boxes" not in truth:
            continue
        stats["photos"] += 1
        img = cv2.imread(path)
        name = Path(path).name
        if name not in cache:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cache[name] = [list(d.bbox) for d in list(decode.scan_stages(gray, decode.LIVE_PASSES))[-1]]
        codes = [tuple(c) for c in cache[name]]
        regions = boxfinder.find_boxes(img)
        flagged = boxfinder.without_code(regions, codes)
        clear = [b for b in truth["boxes"] if b["inside"] and b["visible"] >= 0.75]
        stats["clear"] += len(clear)
        stats["regions"] += len(regions)
        stats["flagged"] += len(flagged)
        for b in clear:
            hit = max(regions, key=lambda r: iou(r, b["bbox"]), default=None)
            matched = hit is not None and iou(hit, b["bbox"]) >= 0.4
            stats["found"] += matched
            decoded = any(contains_centre(b["bbox"], c) for c in codes)
            if not decoded:
                stats["no_code_clear"] += 1
                stats["no_code_flagged"] += bool(matched and hit in flagged)
                if b["code_visible"]:
                    stats["sticker_unread"] += 1
                    stats["sticker_unread_flagged"] += bool(matched and hit in flagged)
                else:
                    stats["sticker_absent"] += 1
                    stats["sticker_absent_flagged"] += bool(matched and hit in flagged)
        for r in regions:
            best = max((iou(r, b["bbox"]) for b in truth["boxes"]), default=0)
            if best < 0.4:
                stats["regions_nonbox"] += 1
                if r in flagged:
                    stats["flagged_nonbox"] += 1
                    nonbox_examples.append((name, r))
            elif r in flagged:
                stats["flagged_true"] += 1
    cache_path.write_text(json.dumps(cache))
    s = stats
    pct = lambda a, b: f"{a}/{b} = {100 * a / b:.1f}%" if b else f"{a}/0"
    print(f"{s['photos']} photos, {s['clear']} clear packs (entirely in frame, 75 % visible or more)")
    print(f"packs found as a region (IoU >= 0.4): {pct(s['found'], s['clear'])}")
    print(f"regions found: {s['regions']}, of which not a pack (sheet, pills, shadows...): {pct(s['regions_nonbox'], s['regions'])}")
    print(f"packs with NO code read: {s['no_code_clear']}  (sticker not on the pack or hidden: {s['sticker_absent']}, sticker there but the scan did not read it: {s['sticker_unread']})")
    print(f"  of them flagged 'no code read': {pct(s['no_code_flagged'], s['no_code_clear'])}  | sticker absent: {pct(s['sticker_absent_flagged'], s['sticker_absent'])}  | sticker unread: {pct(s['sticker_unread_flagged'], s['sticker_unread'])}")
    print(f"flags on screen: {s['flagged']}: on a pack {s['flagged_true']}, on something that is not a pack {s['flagged_nonbox']}")
    for name, r in nonbox_examples[:show]:
        print("  non-pack flag", name, r)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 5)
