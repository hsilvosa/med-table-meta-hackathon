"""The light box finder: packs on an evenly coloured table, which of them have no readable code, and what must NOT be taken for a pack."""

import cv2
import numpy as np

from helpers import ntin_element_string, render_datamatrix
from medtable import boxes, decode

WOOD = (60, 110, 170)       # BGR


def table(w=1600, h=1200):
    rng = np.random.default_rng(1)
    img = np.empty((h, w, 3), np.uint8)
    img[:] = WOOD
    img = np.clip(img.astype(int) + rng.integers(-6, 7, (h, 1, 1)), 0, 255).astype(np.uint8)      # grain: rows a little lighter or darker
    return img


def pack(img, x, y, w=300, h=200, colour=(200, 90, 40), code=None):
    cv2.rectangle(img, (x, y), (x + w, y + h), (245, 245, 245), -1)
    cv2.rectangle(img, (x, y), (x + w // 2, y + h), colour, -1)                    # printed colour
    for i in range(4):
        cv2.putText(img, "MEDICINE 10 MG", (x + w // 2 + 8, y + 40 + i * 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
    if code is not None:
        small = render_datamatrix(code, 4)
        img[y + h - small.shape[0] - 8:y + h - 8, x + w - small.shape[1] - 8:x + w - 8] = small
    return (x, y, x + w, y + h)


def inside(found, expected, tolerance=40):
    return any(all(abs(a - b) <= tolerance for a, b in zip(f, expected)) for f in found)


def scene():
    img = table()
    with_code = pack(img, 150, 150, code=ntin_element_string("654177", "281231", serial="SN1"))
    no_code = pack(img, 800, 200, colour=(60, 160, 40))
    cv2.rectangle(img, (300, 700), (620, 940), (250, 250, 250), -1)                    # a sheet of paper: white, faint grey lines, no colour
    for i in range(14):
        cv2.line(img, (320, 720 + i * 16), (600, 720 + i * 16), (175, 175, 175), 1)
    return img, with_code, no_code


def test_packs_are_found_and_a_sheet_of_paper_is_not():
    img, with_code, no_code = scene()
    found = boxes.find_boxes(img)
    assert inside(found, with_code) and inside(found, no_code)
    assert len(found) == 2                                                      # the sheet at (300, 700) is not reported


def test_only_the_pack_without_a_read_code_is_reported_as_such():
    img, with_code, no_code = scene()
    codes = [d.bbox for d in decode.find_datamatrix(img)]
    assert len(codes) == 1
    left = boxes.without_code(boxes.find_boxes(img), codes)
    assert len(left) == 1 and inside(left, no_code)


def test_tiny_things_and_regions_cut_by_the_border_are_ignored():
    img, _, _ = scene()
    cv2.circle(img, (1300, 900), 18, (255, 255, 255), -1)                         # a loose pill
    cv2.rectangle(img, (1500, 500), (1599, 760), (40, 40, 200), -1)                # a pack cut by the right edge: its code may be outside the photo
    assert len(boxes.find_boxes(img)) == 2


def test_a_plain_strip_or_shadow_without_any_printing_is_not_a_pack():
    img, _, _ = scene()
    cv2.rectangle(img, (1200, 800), (1260, 1000), (30, 70, 120), -1)                  # a dark seam between two boards, 60 px wide and 200 px long
    cv2.rectangle(img, (1000, 900), (1100, 1100), (35, 80, 130), -1)                   # a shadow: darker wood, pack-sized, nothing printed
    assert len(boxes.find_boxes(img)) == 2


def test_an_empty_table_has_no_packs_and_grayscale_input_does_not_crash():
    assert boxes.find_boxes(table()) == []
    assert boxes.find_boxes(cv2.cvtColor(scene()[0], cv2.COLOR_BGR2GRAY)) is not None


def test_a_code_inside_a_region_covers_it_and_one_outside_does_not():
    box = (100, 100, 400, 300)
    assert boxes.without_code([box], [(150, 150, 200, 200)]) == []
    assert boxes.without_code([box], [(500, 150, 550, 200)]) == [box]


def test_on_a_white_table_it_stays_silent_instead_of_guessing():
    img = table()
    img[:] = (232, 234, 236)                                                     # a white table: in the room photos the finder found 13 % there and 4 of its 6 boxes were wrong
    cv2.rectangle(img, (150, 150), (450, 350), (200, 90, 40), -1)                # a pack the finder does see on white (blue all over, white lettering)
    for i in range(4):
        cv2.putText(img, "MEDICINE 10 MG", (160, 205 + i * 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    assert boxes.regions(img)                                                    # it is seen...
    assert boxes.light_table(img) and boxes.find_packs(img) == []               # ...but on a white table nothing is reported
    assert not boxes.light_table(table()) and boxes.find_packs(scene()[0])
