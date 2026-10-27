"""Codes that are too small for a plain read: about 1.9 pixels per module, blurred, rotated, on a busy background (a 12 MP phone at 90 cm).

Measured with this synthetic generator (blur 0.9 px, noise): the plain read fails up to 2.0 px/module and works from 3.0; the zoomed scan reads 6 of 6 from 1.8 and
0 of 6 at 1.6 and below. The 3D-room photos are sharper than this generator, and there the scan reads codes down to about 1.6 px/module.
"""

import cv2
import numpy as np
import pytest
import zxingcpp

from helpers import ntin_element_string, render_datamatrix
from medtable import decode

TEXTS = [ntin_element_string(cn, "281231", f"L{i}", f"SN{i:04d}") for i, cn in enumerate(("654177", "662025", "715240"))]


def photo_with(text: str, px_per_module: float, angle: float, seed: int, blur: float = 0.9, size=(1800, 1300)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = render_datamatrix(text, module_px=16, quiet=2)
    small = cv2.resize(base, None, fx=px_per_module / 16, fy=px_per_module / 16, interpolation=cv2.INTER_AREA)
    background = (150 + 40 * cv2.GaussianBlur(rng.random(size[::-1]).astype(np.float32), (0, 0), 25) / 0.05).clip(60, 220)
    img = cv2.cvtColor(background.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    side = int(np.hypot(*small.shape[:2])) + 2          # room for the corners when the symbol is turned
    padded = cv2.copyMakeBorder(small, (side - small.shape[0]) // 2, side - small.shape[0] - (side - small.shape[0]) // 2,
                                (side - small.shape[1]) // 2, side - small.shape[1] - (side - small.shape[1]) // 2, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    h, w = padded.shape[:2]
    rotated = cv2.warpAffine(padded, cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0), (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    x, y = int(rng.integers(300, size[0] - 300)), int(rng.integers(300, size[1] - 300))
    img[y:y + h, x:x + w] = rotated
    img = cv2.GaussianBlur(img, (0, 0), blur)
    return np.clip(img.astype(np.float32) + rng.normal(0, 3.0, img.shape), 0, 255).astype(np.uint8)


def plain_read(img) -> set[str]:
    return {r.text for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.DataMatrix, text_mode=zxingcpp.TextMode.HRI)}


@pytest.mark.parametrize("seed,angle", [(1, 0), (2, 17), (3, 33), (4, 60), (5, 45), (6, 5)])
def test_a_code_of_1_9_pixels_per_module_is_read_by_the_zoomed_scan(seed, angle):
    img = photo_with(TEXTS[seed % 3], 1.9, angle, seed)
    assert TEXTS[seed % 3] not in plain_read(img)                # the test is meaningful: a plain read of the whole image fails
    found = decode.find_datamatrix(img, libdmtx=False)
    assert [d.text for d in found] == [TEXTS[seed % 3]] and found[0].method == "zxing-zoom"


def test_the_bounding_box_is_in_the_coordinates_of_the_original_image():
    img = photo_with(TEXTS[0], 1.9, 10, 7)
    (detection,) = decode.find_datamatrix(img, libdmtx=False)
    x0, y0, x1, y1 = detection.bbox
    assert 0 <= x0 < x1 <= img.shape[1] and 0 <= y0 < y1 <= img.shape[0] and 20 < x1 - x0 < 90


def test_below_about_one_pixel_per_module_nothing_is_invented():
    img = photo_with(TEXTS[0], 0.8, 10, 8)
    assert decode.find_datamatrix(img, libdmtx=False) == []     # a miss is acceptable; a wrong code never is


def test_a_busy_photo_without_any_code_gives_no_detections():
    rng = np.random.default_rng(9)
    noise = cv2.GaussianBlur(rng.random((1300, 1800, 3)).astype(np.float32), (0, 0), 1.2)
    img = (255 * (noise - noise.min()) / np.ptp(noise)).astype(np.uint8)
    assert decode.find_datamatrix(img, libdmtx=False) == []
