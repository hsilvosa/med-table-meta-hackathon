"""Local server for the 3D room: serves web/ and receives the photos taken with the virtual phone.

  .venv-app/Scripts/python.exe scripts/serve_world.py [--port 8600]

Open http://127.0.0.1:8600 . Photos are saved in data/world_photos/ as photo_<time>.jpg with a .json next to it (the ground
truth: which codes are in view, their pixel size, the CNs, the pose), and copied to latest.jpg / latest.json, which the
Streamlit app can load. Binds to 127.0.0.1 only; nothing leaves the machine.
"""

import argparse
import json
import mimetypes
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


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path not in ("/photo", "/scan"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= MAX_BYTES:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        if self.path == "/scan":
            effects = self.headers.get("X-Effects") == "1"
            live_scan.write_stages(self, live_scan.scan(body, (lambda jpeg: phone_effects(jpeg, int(time.time() * 1000) % 2**32)) if effects else None, thorough=True))      # the room has the time: the whole table is read as hard as a photo, box by box as it goes
            return
        if self.headers.get("X-Effects") == "1":
            body = phone_effects(body, int(time.time() * 1000) % 2**32)
        truth = json.loads(urllib.parse.unquote(self.headers.get("X-Truth", "{}")) or "{}")
        OUT.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        photo = OUT / f"photo_{stamp}.jpg"
        photo.write_bytes(body)
        photo.with_suffix(".json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
        shutil.copyfile(photo, OUT / "latest.jpg")
        shutil.copyfile(photo.with_suffix(".json"), OUT / "latest.json")
        payload = json.dumps({"name": photo.name, "bytes": len(body)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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
