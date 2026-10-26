"""Helpers shared by the tests: render a real GS1 Data Matrix with zxing-cpp."""

import cv2
import numpy as np
import zxingcpp

from medtable import cn


def ntin_element_string(cn6: str, expiry: str = "281231", lot: str = "LOT123", serial: str = "SN0001") -> str:
    """HRI element string of a Spanish pack: (01) is the NTIN '0' + 847000 + CN6 + check digit."""
    return f"(01)0{cn.gtin13(cn6)}(17){expiry}(10){lot}(21){serial}"


def render_datamatrix(element_string: str, module_px: int = 8, quiet: int = 4, background: int = 255) -> np.ndarray:
    """BGR image of a GS1 Data Matrix with `module_px` pixels per module and a quiet zone of `quiet` modules.

    zxing-cpp's own image is exactly one pixel per module, so it is enlarged here without interpolation.
    """
    modules = np.array(zxingcpp.create_barcode(element_string, zxingcpp.BarcodeFormat.DataMatrix, gs1=True).to_image())
    big = cv2.resize(modules, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    big = np.pad(big, quiet * module_px, constant_values=background)
    return cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)
