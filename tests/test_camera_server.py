"""The camera page's server: scans frames, saves photos for the planner, and listens only where it is told to."""

import importlib.util
import json
import shutil
import ssl
import threading
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import pytest

from fixtures import med
from medtable import synthetic
from medtable.resolve import Resolver

WEB = Path(__file__).resolve().parent.parent / "web"


@pytest.fixture
def camera(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("serve_camera", Path(__file__).resolve().parent.parent / "scripts" / "serve_camera.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.chdir(tmp_path)
    spec.loader.exec_module(module)
    known = {"654177": med("654177", "SINTROM 4 mg COMPRIMIDOS", ["ACENOCUMAROL"], "B01AA07")}
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: known.get("".join(c for c in cn if c.isdigit())[:6]))
    servers = []

    def start(**kwargs):
        server = module.make_server(0, directory=str(WEB), **{"lan": False, "https": False, **kwargs})
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return module, server

    yield start, tmp_path
    for server in servers:
        server.shutdown()


def jpeg(items):
    ok, buffer = cv2.imencode(".jpg", synthetic.demo_photo(items))
    assert ok
    return buffer.tobytes()


def post(url, path, body):
    request = urllib.request.Request(url + path, data=body, method="POST", headers={"Content-Type": "image/jpeg"})
    return urllib.request.urlopen(request, timeout=60)


def test_a_frame_is_scanned_in_stages_and_the_code_is_verified(camera):
    start, tmp = camera
    module, server = start()
    with post(f"http://127.0.0.1:{server.server_address[1]}", "/scan", jpeg([("654177", "281231")])) as reply:
        stages = [json.loads(line) for line in reply.read().decode().splitlines() if line]
    assert stages[-1]["done"] and [c["status"] for c in stages[-1]["codes"]] == ["verified"]
    assert stages[-1]["codes"][0]["name"] == "SINTROM 4 mg COMPRIMIDOS"
    assert not (tmp / "data" / "camera_photos").exists()               # a preview frame is never saved


def test_a_photo_is_saved_and_copied_as_latest_and_something_that_is_not_an_image_is_refused(camera):
    start, tmp = camera
    module, server = start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    body = jpeg([("654177", "281231")])
    saved = json.load(post(url, "/photo", body))["saved"]
    folder = tmp / "data" / "camera_photos"
    assert (folder / saved).read_bytes() == body == (folder / "latest.jpg").read_bytes()
    with pytest.raises(urllib.error.HTTPError) as error:
        post(url, "/photo", b"not a picture")
    assert error.value.code == 400 and len(list(folder.glob("photo_*.jpg"))) == 1
    with pytest.raises(urllib.error.HTTPError) as error:
        post(url, "/scan", b"not a picture")
    assert error.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as error:
        post(url, "/other", b"x")
    assert error.value.code == 404


def test_the_page_and_its_modules_are_served(camera):
    start, _ = camera
    module, server = start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    page = urllib.request.urlopen(url + "/camera.html", timeout=10).read().decode()
    assert "Take photo" in page and "camera.js" in page
    for name in ("camera.js", "livescan.js"):
        reply = urllib.request.urlopen(f"{url}/{name}", timeout=10)
        assert reply.headers["Content-Type"].startswith("text/javascript")


def test_it_listens_on_this_computer_only_unless_the_local_network_is_asked_for(camera):
    start, _ = camera
    assert start()[1].server_address[0] == "127.0.0.1"
    assert start(lan=True)[1].server_address[0] == "0.0.0.0"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl makes the self-signed certificate")
def test_https_uses_a_self_signed_certificate_with_a_generic_name(camera):
    start, tmp = camera
    module, server = start(https=True)
    context = ssl.create_default_context()
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    reply = urllib.request.urlopen(f"https://127.0.0.1:{server.server_address[1]}/camera.html", timeout=20, context=context)
    assert b"Take photo" in reply.read()
    pem = (tmp / "data" / "cache" / "cert" / "cert.pem").read_bytes()
    decoded = ssl.PEM_cert_to_DER_cert(pem.decode())
    assert b"med-table-local" in decoded                                 # the only name in the certificate
