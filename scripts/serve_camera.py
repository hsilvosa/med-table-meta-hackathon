"""Local server of the camera page: the same live scan as the 3D room, but with the camera of the device (a webcam, or a phone).

  .venv-app/Scripts/python.exe scripts/serve_camera.py [--port 8700] [--lan] [--https]

Open http://127.0.0.1:8700/camera.html . The page reads frames from the camera, sends them here (/scan: green boxes, amber boxes) and, when the shutter is
pressed, sends the full photo (/photo), which is saved in data/camera_photos/ (photo_<time>.jpg and latest.jpg) for the planner.

By default it listens on 127.0.0.1 only, and nothing leaves the machine. To use a phone on the same Wi-Fi: --lan (listen on the local network; anyone on that
network can then send photos and read the page, so use it at home only) and --https (a phone's browser gives the camera to a page only over https: a
self-signed certificate is made with openssl in data/cache/cert/ and the phone's browser will warn once).
"""

import argparse
import mimetypes
import shutil
import ssl
import subprocess
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from medtable import live_scan  # noqa: E402

mimetypes.add_type("text/javascript", ".js")   # Windows registries often say text/plain, which blocks ES modules
OUT = Path("data/camera_photos")
CERT_DIR = Path("data/cache/cert")
MAX_BYTES = 64 * 1024 * 1024


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
            live_scan.write_stages(self, live_scan.scan(body))
            return
        if cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR) is None:
            self.send_error(400, "not an image")
            return
        OUT.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        photo = OUT / f"photo_{stamp}.jpg"
        photo.write_bytes(body)
        shutil.copyfile(photo, OUT / "latest.jpg")
        payload = b'{"saved": "' + photo.name.encode() + b'"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")      # a demo server: always serve the current files
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:   # keep the console quiet except for photos and errors
        text = fmt % args
        if ("POST /photo" in text) or " 404 " in text or " 500 " in text or " 400 " in text:
            super().log_message(fmt, *args)


def make_certificate() -> tuple[Path, Path]:
    """A self-signed certificate with a generic name (no personal data), made once with openssl."""
    cert, key = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
    if not (cert.exists() and key.exists()):
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30", "-subj", "/CN=med-table-local",
                            "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            raise SystemExit(f"--https needs openssl to make a certificate and it failed: {error}")
    return cert, key


def make_server(port: int, lan: bool, https: bool, directory: str = "web") -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), partial(Handler, directory=directory))
    if https:
        cert, key = make_certificate()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)      # the handshake runs in the request's thread
    return server


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8700)
    ap.add_argument("--lan", action="store_true", help="listen on the local network (for a phone); default: this computer only")
    ap.add_argument("--https", action="store_true", help="serve https with a self-signed certificate (a phone needs it for the camera)")
    args = ap.parse_args()
    server = make_server(args.port, args.lan, args.https)
    scheme = "https" if args.https else "http"
    print(f"camera page on {scheme}://{'0.0.0.0' if args.lan else '127.0.0.1'}:{args.port}/camera.html  (photos -> {OUT})", flush=True)
    if args.lan:
        print("WARNING: listening on the local network. Anyone on it can send photos here. Use it at home, and stop it when you are done.", flush=True)
    server.serve_forever()
