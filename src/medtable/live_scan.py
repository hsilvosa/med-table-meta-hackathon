"""The live preview shared by the 3D room and the camera page: read the codes of one frame, stage by stage, and say what was seen.

A frame goes in as JPEG bytes; what comes out, after the plain read and after each fast zoom pass, is the codes found so far, each with its box and a
verdict (the same three checks as the planner: readable code, valid national code, known to CIMA), and in the last stage the packs where no code was read
(medtable.boxes). Only positions and verdicts go back to the screen. Nothing is saved here, and nothing here decides what the planner uses: that is the photo.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator

import cv2
import numpy as np

from . import advice, boxes, decode, identify
from .resolve import Resolver

_resolver: Resolver | None = None
_scan_lock = threading.Lock()      # one scan at a time: a scan already uses four threads


def resolver() -> Resolver:
    global _resolver
    if _resolver is None:
        _resolver = Resolver("data/cache/cima")
    return _resolver


def scan(jpeg: bytes, prepare: Callable[[bytes], bytes] | None = None, thorough: bool = False) -> Iterator[dict]:
    """Yield everything found so far after the plain read and after each zoom pass; the last dict has "done": true and the packs with no code read.

    `prepare` may change the JPEG first (the room adds the effects of a phone camera). `thorough` reads the frame as hard as a photo (all the passes, more windows): the
    camera page asks for it when a first look left boxes unread. Raises ValueError, before yielding, if the bytes are not an image.
    """
    started = time.time()
    if prepare is not None:
        jpeg = prepare(jpeg)
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("not an image")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    passes = decode.ZOOM_PASSES if thorough else decode.LIVE_PASSES
    last = len(passes)                      # stage 0 is the plain read, then one stage per zoom pass
    with _scan_lock:
        for number, found in enumerate(decode.scan_stages(gray, passes)):
            readings = [identify.read_code(d, resolver()) for d in found]
            codes = [{"bbox": list(r.bbox), "status": r.status, "name": r.medicine.name if r.medicine else None, "expired": r.expired,
                      "problem": r.problems[0] if r.problems else None, "raw": r.raw} for r in readings]
            done = number == last
            extra = {}
            if done:          # said at the end only: which packs have no code read, and what to do about it
                packs = boxes.find_packs(frame)
                nocode = boxes.without_code([p["bbox"] for p in packs], [d.bbox for d in found])
                extra = {"nocode": [list(b) for b in nocode], "advice": advice.advise(gray, packs, [d.bbox for d in found], nocode)}
            yield {"size": [gray.shape[1], gray.shape[0]], "codes": codes, "nocode": [], "ms": int((time.time() - started) * 1000), "done": done, **extra}


def write_stages(handler, stages: Iterator[dict]) -> bool:
    """Send the stages as they are ready: one JSON object per line, the connection closes at the end. False (and a 400) if the frame is not an image."""
    try:
        first = next(stages)            # the image is checked before anything is sent
    except ValueError:
        handler.send_error(400, "not an image")
        return False
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson")
    handler.end_headers()
    try:
        for stage in _chain(first, stages):          # lazily: unpacking the generator would compute every stage before sending the first
            handler.wfile.write(json.dumps(stage).encode() + bytes([10]))
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):       # the screen moved on and dropped the request
        pass
    return True


def _chain(first: dict, rest: Iterator[dict]) -> Iterator[dict]:
    yield first
    yield from rest
