"""A light box finder: where on the table are medicine packs, and which of them have no readable code.

It is classical image processing, not a model: the table is the most common colour in the photo, a pack is a compact region whose colour differs
from the table, of a size a pack can have. It works on a plain, evenly coloured table. It does NOT identify anything: it only says "something pack-sized
is here". The live preview of the room and the planner use it for one thing, to say that a pack was seen and no code was read from it, so that the
caregiver takes a close-up or types the code. It never puts anything in the plan.

Known limits (measured in experiments/eval_boxes.py): it needs a table of a middle tone and packs that stand out from it (on a white table it found
13 % of the packs with 4 of 6 boxes wrong, so on a white table it now reports nothing; on a dark one 71 %); two packs that touch are one region; a pack with almost no printed text is taken for paper and not reported;
anything pack-sized with printed marks on it looks like a pack. A region with almost no dark marks (plain paper, a shadow, a seam between boards)
is never reported: every pack has printed text.
"""

from __future__ import annotations

import cv2
import numpy as np

WORK_WIDTH = 800                    # the image is reduced to this width: a pack is about 100 to 250 px wide there
MIN_AREA, MAX_AREA = 0.005, 0.12    # share of the image a pack can cover (at 90 cm a pack is about 1 to 4 %, at 30 cm about 10 %); the smallest pack in 60 photos was 1.4 %
MIN_FILL = 0.55                     # share of its rotated bounding rectangle a region fills (a pack is a rectangle)
MAX_ASPECT = 4.0
MIN_TEXT = 0.025                    # a pack has printed text and logos: a region with almost no dark marks is a sheet of paper, a shadow or a seam in the wood
LIGHT_TABLE_L, LIGHT_TABLE_CHROMA = 190, 15     # a table this light and this grey (Lab, 0-255 scale) is "white": room white table L 220-227, chroma 6-7; wood L 115-159, chroma 24-34
COLOUR_DISTANCE = 22.0              # distance in Lab from the table colour above which a pixel is "not table"


def _table_colour(lab: np.ndarray) -> np.ndarray:
    """The most common colour: k-means with three clusters on a sample of the pixels, the biggest cluster is the table."""
    sample = lab.reshape(-1, 3)[:: max(1, lab.shape[0] * lab.shape[1] // 6000)].astype(np.float32)
    _, labels, centres = cv2.kmeans(sample, 3, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 2, cv2.KMEANS_PP_CENTERS)
    return centres[np.bincount(labels.ravel()).argmax()]


def _small_lab(img: np.ndarray) -> np.ndarray:
    scale = WORK_WIDTH / img.shape[1]
    small = cv2.resize(img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(cv2.GaussianBlur(small, (0, 0), 1.5), cv2.COLOR_BGR2LAB).astype(np.float32)


def light_table(img: np.ndarray) -> bool:
    """True on a white or very light grey table, where white packs and paper look like the table and the finder is wrong more often than right."""
    L, a, b = _table_colour(_small_lab(img))
    return bool(L >= LIGHT_TABLE_L and np.hypot(a - 128, b - 128) < LIGHT_TABLE_CHROMA)


def regions(img: np.ndarray) -> list[dict]:
    """Every pack-sized region that differs from the table: its box in the coordinates of `img` and two measures of its look inside the region only."""
    h, w = img.shape[:2]
    scale = WORK_WIDTH / w
    small = cv2.resize(img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    blurred = cv2.GaussianBlur(small, (0, 0), 1.5)                # wood grain and sensor noise
    lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)
    table = _table_colour(lab)
    diff = lab - table
    distance = np.sqrt(diff[..., 1] ** 2 + diff[..., 2] ** 2 + (0.5 * diff[..., 0]) ** 2)      # colour first, brightness half as much (shadows)
    mask = (distance > COLOUR_DISTANCE).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    total = small.shape[0] * small.shape[1]
    lab_sharp = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    chroma = np.hypot(lab_sharp[..., 1] - 128, lab_sharp[..., 2] - 128)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    dark = (gray < 150).astype(np.uint8)
    thin_strokes = ((dark > 0) & (cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) == 0))      # dark marks narrower than 5 px: text
    out = []
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if not MIN_AREA <= area / total <= MAX_AREA:
            continue
        if x <= 1 or y <= 1 or x + bw >= small.shape[1] - 1 or y + bh >= small.shape[0] - 1:
            continue                                              # cut by the edge of the photo: its code may be outside
        inside = labels == i
        points = cv2.findNonZero(inside.astype(np.uint8))
        (_, _), (rw, rh), _ = cv2.minAreaRect(points)
        if min(rw, rh) < 1 or max(rw, rh) / min(rw, rh) > MAX_ASPECT or area / (rw * rh) < MIN_FILL:
            continue
        out.append({"bbox": (int(x / scale), int(y / scale), int((x + bw) / scale), int((y + bh) / scale)),
                    "side": float(np.sqrt(rw * rh) / scale),          # side of the square with the same area, in pixels of `img`
                    "colour": float((chroma[inside] > 25).mean()), "text": float(thin_strokes[inside].mean())})
    return out


def find_packs(img: np.ndarray) -> list[dict]:
    """The regions that are packs (see the module text): {"bbox": (x0, y0, x1, y1), "side": pixels} in the coordinates of `img`."""
    if light_table(img):            # silent rather than wrong: a missing amber box never meant "every pack has a code"
        return []
    return [{"bbox": r["bbox"], "side": r["side"]} for r in regions(img) if r["text"] >= MIN_TEXT]


def find_boxes(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Pack-sized regions that differ from the table, as (x0, y0, x1, y1) in the coordinates of `img`. Regions touching the border are left out."""
    return [p["bbox"] for p in find_packs(img)]


def without_code(boxes: list[tuple[int, int, int, int]], codes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """The boxes that contain the centre of no code that was read (readable or not: a code that is read but not verified is another message)."""
    def has_code(box):
        x0, y0, x1, y1 = box
        return any(x0 <= (c[0] + c[2]) / 2 <= x1 and y0 <= (c[1] + c[3]) / 2 <= y1 for c in codes)
    return [b for b in boxes if not has_code(b)]
