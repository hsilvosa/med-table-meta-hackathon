"""The one sentence that tells the person holding the camera what to do: distance, light, focus. Never about a medicine."""

import cv2
import numpy as np

from medtable import advice

RNG = np.random.default_rng(0)
SHARP = (np.kron(RNG.integers(0, 2, (160, 200)), np.ones((4, 4))) * 180 + 40).astype(np.uint8)      # 800 x 640 of 4 px squares: a sharp, well lit frame
BOX = (100, 100, 400, 300)


def pack(side):
    return {"bbox": BOX, "side": side}


def missing(gray, side=500, codes=()):
    return advice.advise(gray, [pack(side)], list(codes), [BOX])


def test_every_pack_has_its_code_read_is_good_news_whatever_the_light():
    for gray in (SHARP, (SHARP * 0.2).astype(np.uint8)):
        said = advice.advise(gray, [pack(500)], [(120, 120, 160, 160)], [])
        assert said["level"] == "good" and said["text"].startswith("1 medicine recognised.")
    assert advice.advise(SHARP, [pack(500), pack(500)], [(1, 1, 2, 2), (3, 3, 4, 4)], [])["text"].startswith("2 medicines recognised.")


def test_nothing_in_view_asks_to_point_the_camera_at_the_table():
    said = advice.advise(SHARP, [], [], [])
    assert said["level"] == "bad" and said["distance"] == "none" and "cannot see any box" in said["text"]


def test_a_pack_too_small_for_its_code_to_be_read_asks_to_come_closer():
    said = missing(SHARP, side=300)                 # 300 px * 0.0044 = 1.3 pixels per module
    assert said["distance"] == "closer" and said["text"].startswith("Move a little closer") and said["px_per_module"] == 1.32
    assert missing(SHARP, side=700)["distance"] == "unread"       # 3.1 px per module: close enough, so the reason is another one


def test_the_light_comes_before_the_distance():
    assert "too dark" in missing((SHARP * 0.25).astype(np.uint8), side=300)["text"]
    glare = np.clip(SHARP.astype(int) + 120, 0, 255).astype(np.uint8)
    assert "too much shine" in missing(glare, side=300)["text"]
    assert advice.light_state(advice.frame_quality(SHARP)) == "ok"


def test_a_blurry_frame_asks_to_hold_steady_but_a_sharp_one_does_not():
    assert "blurry" in missing(cv2.GaussianBlur(SHARP, (0, 0), 1.5), side=700)["text"]
    text = missing(SHARP, side=700)["text"]
    assert "blurry" not in text and "turn them" in text.lower()


def test_a_code_that_was_read_makes_the_missing_boxes_a_mid_level_message():
    said = advice.advise(SHARP, [pack(500), {"bbox": (500, 100, 700, 300), "side": 500}], [(520, 120, 560, 160)], [BOX])
    assert said["level"] == "mid" and said["text"]
