"""Find and read Data Matrix codes in a photo.

zxing-cpp is tried first on the whole image and then on overlapping tiles, upscaled when a tile is small, because a
code on a pack is only a few dozen pixels wide in an overview photo. pylibdmtx is the fallback for what zxing misses.
This module only returns text and position; GS1 parsing is in gs1.py and identification in identify.py.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    method: str  # "zxing", "zxing-tile" or "libdmtx"


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
        for grid in (2, 3, 4):
            for x0, y0, x1, y1 in _tiles(h, w, grid):
                tile = img_bgr[y0:y1, x0:x1]
                scale = 2.0 if max(tile.shape[:2]) < 1200 else 1.0
                if scale != 1.0:
                    tile = cv2.resize(tile, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                found += _zxing(tile, scale, (x0, y0), "zxing-tile")
    found = _merge(found)
    if libdmtx and pylibdmtx is not None and not found:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
        for item in pylibdmtx.decode(gray, timeout=4000):
            r = item.rect  # origin at the bottom-left in libdmtx
            found.append(Detection(item.data.decode("utf-8", "replace"), (r.left, h - r.top - r.height, r.left + r.width, h - r.top), "libdmtx"))
    return found
