"""Does the reading hold up when conditions are bad? Recall and time of the decoder under lighting, blur, noise, compression, rotation and resolution.

  .venv-app/Scripts/python.exe experiments/eval_conditions.py [--photos 12] [--out result.json]

Each condition is applied to the same room photos (seeded, so a run can be repeated) and the share of the codes in the ground truth that are read is
counted. The photos are the 90 cm and 0.5-0.95 m batches of the room: one decoder, many conditions. The degradations are simulations: they say how the
decoder reacts to darkness, blur and so on, not how a particular phone behaves. "dark_avg4" and "noisy_avg4" are the average of four frames with independent noise,
which is what the camera page sends when it looks a second time at a view. "lowres" shrinks photos taken within 0.55 m to 1920 px wide, which gives
a webcam at that distance about the pixels per module that a 12 MP phone has at 90 cm.
"""

import argparse
import glob
import json
import os
import statistics
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, "src")
from medtable import decode  # noqa: E402

FOLDERS = ("data/world_photos_90cm_fresh", "data/world_photos_boxes_heldout")


def noise(img, sigma, seed):
    rng = np.random.default_rng(seed)
    out = img.astype(np.float32)
    for y in range(0, img.shape[0], 500):
        out[y:y + 500] += rng.standard_normal(out[y:y + 500].shape, dtype=np.float32) * sigma
    return np.clip(out, 0, 255).astype(np.uint8)


def jpeg(img, quality):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def rotate(img, angle):
    h, w = img.shape[:2]
    c, s = abs(np.cos(np.radians(angle))), abs(np.sin(np.radians(angle)))
    nw, nh = int(w * c + h * s), int(w * s + h * c)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, m, (nw, nh), borderMode=cv2.BORDER_REPLICATE)


def veil(img):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h:8, 0:w:8].astype(np.float32)
    blob = 90 * np.exp(-(((xx - 0.65 * w) ** 2 + (yy - 0.35 * h) ** 2) / (2 * (0.25 * w) ** 2))) + 40 * (xx / w)
    blob = cv2.resize(blob, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(img.astype(np.float32) * 0.85 + blob[..., None], 0, 255).astype(np.uint8)


def motion(img, length):
    k = np.zeros((length, length), np.float32)
    np.fill_diagonal(k, 1.0 / length)
    return cv2.filter2D(img, -1, k)


CONDITIONS = {
    "clear": lambda img: img,
    "dark": lambda img: noise(np.clip(img.astype(np.float32) * 0.25, 0, 255).astype(np.uint8), 4, 1),
    "very_dark": lambda img: noise(np.clip(img.astype(np.float32) * 0.10, 0, 255).astype(np.uint8), 3, 2),
    "washed_out": veil,
    "overexposed": lambda img: np.clip(img.astype(np.float32) * 1.7 + 25, 0, 255).astype(np.uint8),
    "shake": lambda img: motion(img, 5),
    "defocus": lambda img: cv2.GaussianBlur(img, (0, 0), 1.0),
    "noisy": lambda img: noise(img, 14, 3),
    "jpeg_q25": lambda img: jpeg(img, 25),
    "rot90": lambda img: np.ascontiguousarray(np.rot90(img)),
    "rot180": lambda img: np.ascontiguousarray(np.rot90(img, 2)),
    "rot30": lambda img: rotate(img, 30),
    "dark_avg4": lambda img: np.mean([noise(np.clip(img.astype(np.float32) * 0.25, 0, 255).astype(np.uint8), 4, s).astype(np.float32) for s in range(4)], axis=0).round().astype(np.uint8),
    "noisy_avg4": lambda img: np.mean([noise(img, 14, s).astype(np.float32) for s in range(4)], axis=0).round().astype(np.uint8),
    "dark_noisy_blur": lambda img: noise(cv2.GaussianBlur(np.clip(img.astype(np.float32) * 0.35, 0, 255).astype(np.uint8), (0, 0), 0.7), 8, 4),
}


def pick(n):
    out = []
    for i in range(n):
        files = sorted(glob.glob(f"{FOLDERS[i % 2]}/photo_*.jpg"))
        out.append(files[(i // 2) * (len(files) // (n // 2 + 1)) % len(files)])
    return list(dict.fromkeys(out))


def run(n, out):
    photos = pick(n)
    results = {name: [0, 0, []] for name in list(CONDITIONS) + ["lowres_1920"]}
    for path in photos:
        truth = json.load(open(path.replace(".jpg", ".json")))
        texts = {label["text"] for label in truth["labels"]}
        base = cv2.imread(path)
        for name, fn in list(CONDITIONS.items()) + [("lowres_1920", None)]:
            if name == "lowres_1920":
                if truth["distance_m"] > 0.55:
                    continue
                img = cv2.resize(base, (1920, 1440), interpolation=cv2.INTER_AREA)
            else:
                img = fn(base)
            t = time.perf_counter()
            read = {d.text for d in decode.find_datamatrix(img)}
            elapsed = time.perf_counter() - t
            results[name][0] += len(read & texts)
            results[name][1] += len(texts)
            results[name][2].append(elapsed)
    table = {}
    for name, (hits, total, times) in results.items():
        if total:
            table[name] = dict(recall=round(hits / total, 3), hits=hits, codes=total, mean_s=round(statistics.mean(times), 2))
            print(f"{name:16} {hits:3}/{total:3} = {100 * hits / total:5.1f} %   {statistics.mean(times):5.2f} s per photo", flush=True)
    if out:
        json.dump(table, open(out, "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", type=int, default=12)
    ap.add_argument("--out")
    args = ap.parse_args()
    run(args.photos, args.out)
