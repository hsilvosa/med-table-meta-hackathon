"""Local server for the 3D room: serves web/ and receives the photos taken with the virtual phone.

  .venv-app/Scripts/python.exe scripts/serve_world.py [--port 8600]

Serves the room built by scripts/build_world.py (web/world) or, in a fresh clone, the small room shipped in web/world_demo.
Open http://127.0.0.1:8600 . Photos are saved in data/world_photos/ as photo_<time>.jpg with a .json next to it (the ground
truth: which codes are in view, their pixel size, the CNs, the pose), and copied to latest.jpg / latest.json, which the
Streamlit app can load. Binds to 127.0.0.1 only; nothing leaves the machine.
"""

import argparse
import json
import mimetypes
import os
import re
import threading
import shutil
import sys
import time
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from medtable import decode, live_scan  # noqa: E402       (decode: the tests replace its scan_stages)

mimetypes.add_type("text/javascript", ".js")   # Windows registries often say text/plain, which blocks ES modules
OUT = Path("data/world_photos")
PUBLIC = os.environ.get("PUBLIC_DEMO") == "1"      # the online demo: each visitor's photos in their own folder, deleted after an hour
KEEP_S = 3600
SCANS = threading.BoundedSemaphore(1 if PUBLIC else 8)      # a small shared server (512 MB): live scans wait their turn, one at a time
MAX_BYTES = 64 * 1024 * 1024


def phone_effects(jpeg: bytes, seed: int) -> bytes:
    """A little of what a real phone does: slight defocus, sensor noise, a second JPEG pass. Mild on purpose."""
    rng = np.random.default_rng(seed)
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    scale = img.shape[1] / 4000          # a 48 MP sensor has smaller pixels behind the same lens: the same blur spans more of them and each is noisier
    img = cv2.GaussianBlur(img, (0, 0), 0.9 * scale)
    for y in range(0, img.shape[0], 500):          # in bands: float noise for a whole 48 MP photo would need more than a gigabyte
        band = img[y:y + 500].astype(np.float32) + rng.standard_normal(img[y:y + 500].shape, dtype=np.float32) * (3.0 * scale ** 0.5)
        img[y:y + 500] = np.clip(band, 0, 255).astype(np.uint8)
    ok, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buffer.tobytes() if ok else jpeg


def shrink(jpeg: bytes) -> bytes:
    """Online demo (512 MB): a photo of more than 16 MP is decoded at half size (a quarter of the pixels, 48 MP -> 12 MP) and saved again."""
    if not PUBLIC:
        return jpeg
    if jpeg[:2] != bytes([0xFF, 0xD8]):
        return jpeg
    i, width, height = 2, 0, 0
    while i + 9 < len(jpeg) and jpeg[i] == 0xFF:      # walk the segments to the frame header: the size is read without decoding
        if jpeg[i + 1] in (0xC0, 0xC1, 0xC2):
            height, width = int.from_bytes(jpeg[i + 5:i + 7], "big"), int.from_bytes(jpeg[i + 7:i + 9], "big")
            break
        i += 2 + int.from_bytes(jpeg[i + 2:i + 4], "big")
    if width * height <= 16_000_000:
        return jpeg
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
    ok, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 93]) if img is not None else (False, None)
    return buffer.tobytes() if ok else jpeg


def forget_old_photos() -> None:
    """Online demo: delete the photo folders of visitors who took no photo in the last hour."""
    for folder in OUT.glob("*/"):
        if folder.is_dir() and time.time() - folder.stat().st_mtime > KEEP_S:
            shutil.rmtree(folder, ignore_errors=True)


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path not in ("/photo", "/scan"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= MAX_BYTES:
            self.send_error(413)
            return
        body = shrink(self.rfile.read(length))
        if self.path == "/scan":
            effects = self.headers.get("X-Effects") == "1"
            with SCANS:
                live_scan.write_stages(self, live_scan.scan(body, (lambda jpeg: phone_effects(jpeg, int(time.time() * 1000) % 2**32)) if effects else None, thorough=True))      # the room has the time: the whole table is read as hard as a photo, box by box as it goes
            return
        if self.headers.get("X-Effects") == "1":
            body = phone_effects(body, int(time.time() * 1000) % 2**32)
        truth = json.loads(urllib.parse.unquote(self.headers.get("X-Truth", "{}")) or "{}")
        out = OUT
        if PUBLIC:
            session = self.headers.get("X-Session", "")
            if not re.fullmatch(r"[a-z0-9-]{8,40}", session):
                self.send_error(400, "missing visitor session")
                return
            forget_old_photos()
            out = OUT / session
        out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        photo = out / f"photo_{stamp}.jpg"
        photo.write_bytes(body)
        photo.with_suffix(".json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
        shutil.copyfile(photo, out / "latest.jpg")
        shutil.copyfile(photo.with_suffix(".json"), out / "latest.json")
        payload = json.dumps({"name": photo.name, "bytes": len(body)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        page = urllib.parse.urlsplit(self.path).path
        if PUBLIC and page in ("/camera.html", "/camera.js"):       # a real camera on a shared server: only in the local installation
            self.send_error(404, "The camera page runs only in the local installation")
            return
        if PUBLIC and page == "/":
            self.path = "/welcome.html"
        super().do_GET()

    def translate_path(self, path: str) -> str:
        """The room built on this machine (web/world) when there is one, else the small room shipped in the repository (web/world_demo)."""
        local = super().translate_path(path)
        if path.startswith("/world/") and not (Path(self.directory) / "world" / "world.json").exists():
            return super().translate_path("/world_demo/" + path[len("/world/"):])
        return local

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")      # a demo server: always serve the current files, never a stale main.js
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:   # keep the console quiet except for photos and errors
        if ("POST" in (fmt % args) and "/scan" not in (fmt % args)) or " 404 " in (fmt % args) or " 500 " in (fmt % args):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8600)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory="web"))
    print(f"3D room on http://127.0.0.1:{args.port}  (photos -> {OUT})", flush=True)
    server.serve_forever()
