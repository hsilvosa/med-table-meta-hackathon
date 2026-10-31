"""Plain-language advice for the person holding the camera: is the distance right, is there enough light, is the picture sharp.

The live preview of the 3D room and the camera page show one sentence from here. It is computed from the frame and from what the reader found in it, so
it is the same for a phone, a webcam and the room; the page only displays it. It never says anything about a medicine: only how to hold the camera.

Numbers that come from measurements are named and explained next to their definition (experiments/calibrate_advice.py shows how they were found).
"""

from __future__ import annotations

import cv2
import numpy as np

MODULE_PER_PACK_SIDE = 0.0044       # pixels per module of the code per pixel of the side of the pack (square with the same area): median of 40 codes in the room photos, 10-90 % range 0.0040-0.0051
MIN_PX_PER_MODULE = 1.6             # below this even the enlarged windows rarely read a code (about 1.5 pixels per module is the limit of the 90 cm reading); the camera is too far for its resolution
DARK_MEAN = 80                      # mean grey level of the frame below which it is too dark (room photos: 119-146 normal, 29-36 two stops under, 11-14 darker)
BRIGHT_MEAN, BURNT_SHARE = 152, 0.03   # mean grey level above, or share of burnt-out pixels above, which means glare or over-exposure (normal photos: up to 146 and none burnt; veiled 156+, over-exposed 214+)
BLUR_RATIO = 0.64                   # fine detail over medium detail (90th percentile of 40 px blocks): sharp photos 0.62-0.78, shaken 0.45-0.62, out of focus 0.52-0.66, all simulated


def frame_quality(gray: np.ndarray) -> dict:
    """Light and sharpness of a grey frame, from a reduced copy (cheap): {"mean", "burnt", "blur_ratio"}."""
    w = gray.shape[1]
    small = cv2.resize(gray, None, fx=1600 / w, fy=1600 / w, interpolation=cv2.INTER_AREA) if w > 1600 else gray
    f = small.astype(np.float32)
    g1, g3 = cv2.GaussianBlur(f, (0, 0), 1.0), cv2.GaussianBlur(f, (0, 0), 3.0)
    h, ww = (f.shape[0] // 40) * 40, (f.shape[1] // 40) * 40
    fine = np.abs(f - g1)[:h, :ww].reshape(h // 40, 40, ww // 40, 40).mean(axis=(1, 3))
    medium = np.abs(g1 - g3)[:h, :ww].reshape(h // 40, 40, ww // 40, 40).mean(axis=(1, 3))
    textured = medium > 2.0
    ratio = float(np.percentile(fine[textured] / medium[textured], 90)) if textured.sum() > 5 else None
    return {"mean": float(f.mean()), "burnt": float((small >= 250).mean()), "blur_ratio": ratio}


def light_state(q: dict) -> str:
    if q["mean"] < DARK_MEAN:
        return "dark"
    if q["mean"] > BRIGHT_MEAN or q["burnt"] > BURNT_SHARE:
        return "glare"
    return "ok"


def expected_px_per_module(packs: list[dict]) -> float | None:
    """How many pixels one module of a code would have on the packs seen, judged by the size of the packs (None when no pack was seen)."""
    sides = [p["side"] for p in packs]
    return float(np.median(sides) * MODULE_PER_PACK_SIDE) if sides else None


def advise(gray: np.ndarray, packs: list[dict], codes: list[tuple], nocode: list[tuple]) -> dict:
    """One sentence and a level ("good", "mid", "bad") for what the camera sees.

    `packs`: the pack regions found ({"bbox", "side"}); `codes`: boxes of the codes that were read; `nocode`: boxes of the packs where none was read.
    """
    quality = frame_quality(gray)
    light = light_state(quality)
    missing = [p for p in packs if tuple(p["bbox"]) in {tuple(b) for b in nocode}]
    per_module = expected_px_per_module(missing)
    if codes and not nocode:
        n = len(codes)
        text, level, distance = f"{n} medicine{'s' if n != 1 else ''} recognised. Take the photo when all your boxes are marked.", "good", "good"
    elif not packs and not codes:
        text, level, distance = "No box in view. Point the camera at the table with the boxes.", "bad", "none"
    else:
        level = "mid" if codes else "bad"
        if light == "dark":
            text, distance = "It is too dark. Turn on a light or move to a brighter place.", "unread"
        elif light == "glare":
            text, distance = "There is too much shine. Tilt the box or the camera a little so the shine moves off the code.", "unread"
        elif per_module is not None and per_module < MIN_PX_PER_MODULE:
            text, distance = "Move a little closer to the boxes.", "closer"
        elif not codes and quality["blur_ratio"] is not None and quality["blur_ratio"] < BLUR_RATIO:      # codes being read: the blur is not what stops the rest
            text, distance = "The picture looks blurry. Hold the camera steady and wait a moment for it to focus.", "unread"
        else:
            text, distance = "Some boxes have no code read. Turn them so the printed code faces up and hold the camera steady, or add them by hand.", "unread"
    return {"text": text, "level": level, "distance": distance, "light": light, "blurry": bool(quality["blur_ratio"] is not None and quality["blur_ratio"] < BLUR_RATIO), "px_per_module": None if per_module is None else round(per_module, 2)}
