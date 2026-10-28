"""Synthetic GS1 Data Matrix codes and a demo photo. For tests and the demo only: these are rendered by our own code, so
reading them back says nothing about real packs."""

from __future__ import annotations

import cv2
import numpy as np
import zxingcpp

from . import cn


def ntin_element_string(cn6: str, expiry: str = "281231", lot: str = "LOT123", serial: str = "SN0001") -> str:
    """HRI element string of a Spanish pack: (01) is the NTIN '0' + 847000 + CN6 + check digit."""
    return f"(01)0{cn.gtin13(cn6)}(17){expiry}(10){lot}(21){serial}"


def _modules(element_string: str, square: bool) -> np.ndarray:
    """The modules (0 = black) of a GS1 Data Matrix for the element string. Packs carry a square symbol; zxing-cpp picks the smallest area, which for some strings is a
    long rectangle, so `square` tries the square sizes from the smallest up (version 1 is 10x10, version 7 is 22x22)."""
    if not square:
        return np.array(zxingcpp.create_barcode(element_string, zxingcpp.BarcodeFormat.DataMatrix, gs1=True).to_image())
    for version in range(1, 25):
        try:
            return np.array(zxingcpp.create_barcode(element_string, zxingcpp.BarcodeFormat.DataMatrix, gs1=True, version=version).to_image())
        except ValueError:          # too long for this size
            continue
    raise ValueError("the element string does not fit in any square Data Matrix")


def render_datamatrix(element_string: str, module_px: int = 8, quiet: int = 4, background: int = 255, square: bool = True) -> np.ndarray:
    """BGR image of a GS1 Data Matrix carrying the human-readable element string, `module_px` pixels per module, quiet zone of `quiet` modules.

    `square=True` (default) writes a square symbol (22x22 to 26x26 modules for these strings, like real packs); `square=False` the smallest symbol.
    """
    big = cv2.resize(_modules(element_string, square), None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    big = np.pad(big, quiet * module_px, constant_values=background)
    return cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)


def demo_photo(items: list[tuple[str, str]], size: tuple[int, int] = (1600, 1000), module_px: int = 7) -> np.ndarray:
    """A plain table with one code per (cn6, expiry YYMMDD) in a grid. Not a photo of real packs."""
    w, h = size
    canvas = np.full((h, w, 3), 196, np.uint8)
    cols = 3
    for i, (cn6, expiry) in enumerate(items):
        code = render_datamatrix(ntin_element_string(cn6, expiry, serial=f"SN{i:04d}"), module_px)
        x, y = 60 + (i % cols) * (w // cols), 60 + (i // cols) * (h // 2)
        canvas[y:y + code.shape[0], x:x + code.shape[1]] = code
    return canvas
