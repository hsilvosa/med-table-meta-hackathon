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


def test_a_pack_too_small_for_its_code_to_be_read_asks_to_come_closer():
    said = missing(SHARP, side=300)                 # 300 px * 0.0044 = 1.3 pixels per module
    assert said["distance"] == "closer" and said["text"].startswith("Move a little closer") and said["px_per_module"] == 1.32
    assert missing(SHARP, side=700)["distance"] == "unread"       # 3.1 px per module: close enough, so the reason is another one


def test_the_light_comes_before_the_distance():
    assert "too dark" in missing((SHARP * 0.25).astype(np.uint8), side=300)["text"]
    glare = np.clip(SHARP.astype(int) + 120, 0, 255).astype(np.uint8)
    assert "too much shine" in missing(glare, side=300)["text"]
    assert advice.light_state(advice.frame_quality(SHARP)) == "ok"
    assert "blurry" in missing(cv2.GaussianBlur(SHARP, (0, 0), 1.5), side=700)["text"] and "blurry" not in missing(SHARP, side=700)["text"]
