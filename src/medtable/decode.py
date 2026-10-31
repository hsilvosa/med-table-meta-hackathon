"""Find and read Data Matrix codes in a photo.

zxing-cpp is tried first on the whole image, and then on the most promising windows of the image, which are enlarged and sharpened: the code on a pack
is only a few dozen pixels wide in an overview photo (about 1.5 pixels per module at 90 cm with a 12 MP phone), too coarse for a decoder to sample but
still holding the information (39 of 40 such codes in an early probe, against 9 % for the whole-image read).

Which windows: the image is cut into overlapping square windows and ranked by how much fine detail they hold (a printed code is a dense pattern of
small black and white squares, wood, walls and plain cartons are not); only the best third is enlarged. Each window first gets its contrast stretched
(dark, washed-out and over-exposed photos have all their information in a narrow range of grey) and, if it is noisy, a light smoothing.

This module only returns text and position; GS1 parsing is in gs1.py and identification in identify.py.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import cv2
import numpy as np
import zxingcpp


@dataclass(frozen=True)
class Detection:
    text: str
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 in the original image
    method: str  # "zxing" (the whole image) or "zxing-zoom" (an enlarged window)


ZOOM_TILE, ZOOM_STRIDE = 640, 448        # a code is about 25 to 120 px wide in a 12 MP photo; the overlap (192 px) is larger than any of them
# (enlargement, treatment): the first pass is gentle and cheap, the others are what rescues codes of about 1.5 pixels per module
ZOOM_PASSES = ((2.0, "soft"), (3.0, "strong"), (4.0, "strong"), (3.0, "adaptive_sharp"))
# The live preview scans a frame every second or so, so it uses only the first two passes (about 93 % instead of 98 % of the codes at 90 cm, in
# about a third of the time)
LIVE_PASSES = ZOOM_PASSES[:2]
TILE_SHARE, MIN_TILES = 0.30, 6          # share of the windows that get enlarged, ranked by fine detail (all the codes of 24 test photos were in the best 30 %)
LIVE_TILE_SHARE = 0.20                   # the live preview looks at fewer: it looks again, and a photo is always read with TILE_SHARE (recall 94.7 % instead of 96.8 %, a third faster)
MIN_RANGE = 12                           # a window whose grey levels span less than this holds nothing to decode
FULL_RANGE = 200                         # a window that spans at least this much is left alone; a duller one is stretched
MIN_FINE, FINE_NOISE_FACTOR = 4, 5.0     # a pixel is a small sharp detail if it differs from its surroundings by more than max(MIN_FINE, FINE_NOISE_FACTOR x the median difference)
MIN_FINE_SHARE = 0.0005                  # a window needs this share of such pixels to be worth enlarging
CLEAN_SIGMA = 0.8                        # the "clean" treatment smooths a window this much before enlarging it: for noisy photos, where sharpening alone amplifies the noise
_WORKERS = max(1, min(2 if os.environ.get("PUBLIC_DEMO") == "1" else 4, os.cpu_count() or 1))        # four threads at most: zxing releases the GIL, and the computer stays usable
_pool = ThreadPoolExecutor(max_workers=_WORKERS)


def _zxing(img: np.ndarray, scale: float, origin: tuple[int, int], method: str, *, rotate: bool = False, downscale: bool = False) -> list[Detection]:
    """Read the Data Matrix codes of `img`. `rotate` also tries the picture turned (boxes lie at any angle: without it only 38 % of the codes of the room photos are read), `downscale` also tries it at smaller sizes (worth it only on a whole photo)."""
    found = []
    for code in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.DataMatrix, text_mode=zxingcpp.TextMode.HRI,
                                       try_rotate=rotate, try_downscale=downscale):
        if not code.valid:
            continue
        pts = code.position
        xs = [p.x for p in (pts.top_left, pts.top_right, pts.bottom_right, pts.bottom_left)]
        ys = [p.y for p in (pts.top_left, pts.top_right, pts.bottom_right, pts.bottom_left)]
        box = (int(min(xs) / scale) + origin[0], int(min(ys) / scale) + origin[1],
               int(max(xs) / scale) + origin[0], int(max(ys) / scale) + origin[1])
        found.append(Detection(code.text, box, method))
    return found


def _starts(size: int, tile: int, stride: int) -> list[int]:
    starts = list(range(0, max(size - tile, 0) + 1, stride))
    if starts[-1] + tile < size:
        starts.append(size - tile)
    return starts


def _stretch(window: np.ndarray) -> np.ndarray | None:
    """Spread the grey levels of a dull window (dark, washed-out, over-exposed) over 0..255; a window that already spans most of the range is returned as it is.

    The ends are the 0.005 % and 99.995 % levels, not harder cuts: a small code is only a few hundred pixels of a window, and its black modules must not be clipped.
    None when the window holds too little contrast to be worth reading.
    """
    counts = np.bincount(window.ravel(), minlength=256).cumsum()
    lo, hi = int(np.searchsorted(counts, counts[-1] * 0.00005)), int(np.searchsorted(counts, counts[-1] * 0.99995))
    if hi - lo < MIN_RANGE:
        return None
    if hi - lo >= FULL_RANGE:
        return window
    gain = 255.0 / (hi - lo)
    return cv2.convertScaleAbs(window, alpha=gain, beta=-lo * gain)


def _enhance(up: np.ndarray, scale: float, how: str) -> np.ndarray:
    if how == "soft":
        return cv2.addWeighted(up, 2.2, cv2.GaussianBlur(up, (0, 0), 0.6 * scale), -1.2, 0)
    if how == "strong":     # a wide, heavy unsharp mask: the lens blur of a phone is about the size of a module here
        return cv2.addWeighted(up, 3.0, cv2.GaussianBlur(up, (0, 0), 0.9 * scale), -2.0, 0)
    sharp = cv2.addWeighted(up, 3.0, cv2.GaussianBlur(up, (0, 0), 0.9 * scale), -2.0, 0)       # "adaptive_sharp": threshold the strongly sharpened image
    return cv2.adaptiveThreshold(sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, int(scale * 12) | 1, 4)


def _zoom_tile(gray: np.ndarray, x0: int, y0: int, tile: int, scale: float, how: str, prepared: dict) -> list[Detection]:
    key = (x0, y0)
    if key not in prepared:       # stretched once per window and shared by the passes (a benign race: two threads may both do it)
        prepared[key] = _stretch(gray[y0:y0 + tile, x0:x0 + tile])
    window = prepared[key]
    if window is None:
        return []
    if how == "clean":
        window, how = cv2.GaussianBlur(window, (0, 0), CLEAN_SIGMA), "strong"
    up = cv2.resize(window, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1.0 else window
    return _zxing(_enhance(up, scale, how), scale, (x0, y0), "zxing-zoom", rotate=True)


def _best_tiles(gray: np.ndarray, tile: int, stride: int, share: float) -> list[tuple[int, int]]:
    """Top-left corners of the windows with the most small, sharp squares, best first.

    A pixel counts when it differs from its surroundings by clearly more than the noise of the picture (five times the median difference, and at least 4 grey
    levels): that is what a printed code is made of, and it still stands out of the noise in a dark or grainy photo, where the average difference of a
    window would not. Windows with hardly any such pixels are left out; if every window is like that the best three are tried anyway.
    """
    h, w = gray.shape[:2]
    fine = cv2.absdiff(gray, cv2.GaussianBlur(gray, (0, 0), 1.5))       # what changes from one pixel to the next
    threshold = max(MIN_FINE, FINE_NOISE_FACTOR * float(np.median(fine[::4, ::4])))
    integral = cv2.integral((fine > threshold).astype(np.uint8), sdepth=cv2.CV_32S)
    corners = [(x, y) for y in _starts(h, tile, stride) for x in _starts(w, tile, stride)]
    scores = {}
    for x, y in corners:
        x1, y1 = min(x + tile, w), min(y + tile, h)
        scores[(x, y)] = (integral[y1, x1] - integral[y, x1] - integral[y1, x] + integral[y, x]) / max((x1 - x) * (y1 - y), 1)
    ranked = sorted(corners, key=scores.get, reverse=True)
    chosen = ranked[:max(MIN_TILES, int(np.ceil(len(ranked) * share)))]
    return [c for c in chosen if scores[c] >= MIN_FINE_SHARE] or ranked[:3]


class _Plan:
    """What is decided once per image: the size of the windows and which ones are worth enlarging. Shared by the passes."""

    def __init__(self, gray: np.ndarray, share: float = TILE_SHARE) -> None:
        self.unit = max(gray.shape[1] / 4000, 1.0)
        self.tile, stride = int(ZOOM_TILE * self.unit), int(ZOOM_STRIDE * self.unit)
        self.tiles = _best_tiles(gray, self.tile, stride, share)
        self.prepared: dict = {}

    def run(self, gray: np.ndarray, one_pass: tuple) -> list[Detection]:
        scale = round(max(one_pass[0] / self.unit, 1.0), 2)
        jobs = [(x0, y0, self.tile, scale, one_pass[1]) for x0, y0 in self.tiles]
        return [d for result in _pool.map(lambda job: _zoom_tile(gray, *job, self.prepared), jobs) for d in result]


def find_zoomed(gray: np.ndarray, passes: tuple | None = None) -> list[Detection]:
    """Enlarge and sharpen the windows with the most fine detail and read them. Finds codes that are too small for a read of the whole image.

    The window and the enlargement are in units of a 12 MP photo (4000 px wide): in a 48 MP photo a code is twice as wide in pixels, so the windows are
    twice as big and the enlargement is halved (never below 1), which keeps the cost per photo roughly in line with a 12 MP one.
    """
    plan = _Plan(gray)
    done, found = set(), []
    for one_pass in passes or ZOOM_PASSES:
        key = (round(max(one_pass[0] / plan.unit, 1.0), 2), one_pass[1])
        if key not in done:          # a pass that comes out the same as an earlier one at this image size is not repeated
            done.add(key)
            found += plan.run(gray, one_pass)
    return found


def _merge(found: list[Detection]) -> list[Detection]:
    """One detection per distinct text (the same pack seen in overlapping tiles), keeping the earliest method."""
    seen: dict[str, Detection] = {}
    for d in found:
        seen.setdefault(d.text, d)
    return list(seen.values())


def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def scan_stages(gray: np.ndarray, passes: tuple | None = None):
    """Like find_datamatrix, but yields the codes found so far after the plain read and after each zoom pass (for a live preview)."""
    found = _merge(_zxing(gray, 1.0, (0, 0), "zxing", rotate=True, downscale=True))
    yield found
    plan = _Plan(gray, LIVE_TILE_SHARE if passes == LIVE_PASSES else TILE_SHARE)   # (default passes or any others: the full share)
    for one_pass in passes or ZOOM_PASSES:
        found = _merge(found + plan.run(gray, one_pass))
        yield found


def find_datamatrix(img: np.ndarray, *, tiles: bool = True, passes: tuple | None = None) -> list[Detection]:
    """Return every readable Data Matrix in the image (BGR or grayscale array). `passes` replaces ZOOM_PASSES (a faster, less thorough scan)."""
    gray = _gray(img)
    found = _zxing(gray, 1.0, (0, 0), "zxing", rotate=True, downscale=True)
    if tiles:
        found += find_zoomed(gray, passes)
    return _merge(found)
