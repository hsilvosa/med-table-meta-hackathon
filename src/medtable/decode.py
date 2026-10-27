"""Find and read Data Matrix codes in a photo.

zxing-cpp is tried first on the whole image and then on a dense scan of overlapping tiles that are enlarged 2x and 3x and sharpened:
the code on a pack is only a few dozen pixels wide in an overview photo (about 1.5 pixels per module at 90 cm with a 12 MP phone),
too coarse for a decoder to sample but still holding the information; enlarging and sharpening a small window around it recovers
it (39 of 40 such codes in experiments/lowres_probe.py, against 9 % for the whole-image read). pylibdmtx is the last fallback.
This module only returns text and position; GS1 parsing is in gs1.py and identification in identify.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import zxingcpp

try:  # libdmtx ships a DLL on Windows wheels; if it cannot load, zxing-cpp alone is used
    from pylibdmtx import pylibdmtx
except Exception:  # noqa: BLE001
    pylibdmtx = None


@dataclass(frozen=True)
class Detection:
    text: str
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 in the original image
    method: str  # "zxing", "zxing-zoom" or "libdmtx"


def _zxing(img: np.ndarray, scale: float, origin: tuple[int, int], method: str) -> list[Detection]:
    found = []
    for code in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.DataMatrix, text_mode=zxingcpp.TextMode.HRI):
        if not code.valid:
            continue
        pts = code.position
        xs = [p.x for p in (pts.top_left, pts.top_right, pts.bottom_right, pts.bottom_left)]
        ys = [p.y for p in (pts.top_left, pts.top_right, pts.bottom_right, pts.bottom_left)]
        box = (int(min(xs) / scale) + origin[0], int(min(ys) / scale) + origin[1],
               int(max(xs) / scale) + origin[0], int(max(ys) / scale) + origin[1])
        found.append(Detection(code.text, box, method))
    return found


def _tiles(h: int, w: int, grid: int, overlap: float = 0.25):
    th, tw = h / grid, w / grid
    for r in range(grid):
        for c in range(grid):
            y0, x0 = max(int(r * th - overlap * th), 0), max(int(c * tw - overlap * tw), 0)
            y1, x1 = min(int((r + 1) * th + overlap * th), h), min(int((c + 1) * tw + overlap * tw), w)
            yield x0, y0, x1, y1


ZOOM_TILE, ZOOM_STRIDE = 640, 448        # a code is about 25 to 120 px wide in a 12 MP photo; the overlap (192 px) is larger than any of them
# (enlargement, treatment): the first pass is gentle and cheap, the others are what rescues codes of about 1.5 pixels per module
ZOOM_PASSES = ((2.0, "soft"), (3.0, "strong"), (4.0, "strong"), (3.0, "adaptive_sharp"))
MIN_TILE_CONTRAST = 6.0                   # plain walls and floor have nothing to decode


def _starts(size: int, tile: int, stride: int) -> list[int]:
    starts = list(range(0, max(size - tile, 0) + 1, stride))
    if starts[-1] + tile < size:
        starts.append(size - tile)
    return starts


def _enhance(up: np.ndarray, scale: float, how: str) -> np.ndarray:
    if how == "soft":
        return cv2.addWeighted(up, 2.2, cv2.GaussianBlur(up, (0, 0), 0.6 * scale), -1.2, 0)
    if how == "strong":     # a wide, heavy unsharp mask: the lens blur of a phone is about the size of a module here
        return cv2.addWeighted(up, 3.0, cv2.GaussianBlur(up, (0, 0), 0.9 * scale), -2.0, 0)
    if how == "adaptive":
        return cv2.adaptiveThreshold(up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, int(scale * 8) | 1, 5)
    sharp = cv2.addWeighted(up, 3.0, cv2.GaussianBlur(up, (0, 0), 0.9 * scale), -2.0, 0)       # "adaptive_sharp": threshold the strongly sharpened image
    return cv2.adaptiveThreshold(sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, int(scale * 12) | 1, 4)


def _zoom_tile(gray: np.ndarray, x0: int, y0: int, tile: int, scale: float, how: str) -> list[Detection]:
    window = gray[y0:y0 + tile, x0:x0 + tile]
    if float(window.std()) < MIN_TILE_CONTRAST:
        return []
    up = cv2.resize(window, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1.0 else window
    return _zxing(_enhance(up, scale, how), scale, (x0, y0), "zxing-zoom")


def find_zoomed(gray: np.ndarray, passes: tuple | None = None) -> list[Detection]:
    """Dense scan of overlapping windows, each enlarged and sharpened. Finds codes that are too small for a read of the whole image.

    The window and the enlargement are in units of a 12 MP photo (4000 px wide): in a 48 MP photo a code is twice as wide in pixels, so the windows are
    twice as big and the enlargement is halved (never below 1), which keeps the cost per photo roughly in line with a 12 MP one.
    """
    h, w = gray.shape[:2]
    unit = max(w / 4000, 1.0)
    tile, stride = int(ZOOM_TILE * unit), int(ZOOM_STRIDE * unit)
    scaled = dict.fromkeys((round(max(s / unit, 1.0), 2), how) for s, how in (passes or ZOOM_PASSES))      # de-duplicated, order kept
    jobs = [(x0, y0, tile, s, how) for s, how in scaled for y0 in _starts(h, tile, stride) for x0 in _starts(w, tile, stride)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(lambda job: _zoom_tile(gray, *job), jobs)
    return [d for result in results for d in result]


def _merge(found: list[Detection]) -> list[Detection]:
    """One detection per distinct text (the same pack seen in overlapping tiles), keeping the earliest method."""
    seen: dict[str, Detection] = {}
    for d in found:
        seen.setdefault(d.text, d)
    return list(seen.values())


def find_datamatrix(img_bgr: np.ndarray, *, tiles: bool = True, libdmtx: bool = True) -> list[Detection]:
    """Return every readable Data Matrix in the image (BGR or grayscale array)."""
    h, w = img_bgr.shape[:2]
    found = _zxing(img_bgr, 1.0, (0, 0), "zxing")
    if tiles:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
        found += find_zoomed(gray)
    found = _merge(found)
    if libdmtx and pylibdmtx is not None and not found:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
        for item in pylibdmtx.decode(gray, timeout=4000):
            r = item.rect  # origin at the bottom-left in libdmtx
            found.append(Detection(item.data.decode("utf-8", "replace"), (r.left, h - r.top - r.height, r.left + r.width, h - r.top), "libdmtx"))
    return found
