"""The live preview: the box finder, the staged /scan answer of the room server, and the camera server that stays on this computer."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest
from fixtures import med, ntin_element_string, render_datamatrix

from medtable import advice, boxes, decode, synthetic
from medtable.resolve import Resolver

ROOT = Path(__file__).resolve().parent.parent


def table(colour=(60, 110, 170)):
    img = np.empty((1200, 1600, 3), np.uint8)
    img[:] = colour
    return np.clip(img.astype(int) + np.random.default_rng(1).integers(-6, 7, (1200, 1, 1)), 0, 255).astype(np.uint8)      # wood grain


def put_pack(img, x, y, colour, code=None):
    cv2.rectangle(img, (x, y), (x + 300, y + 200), (245, 245, 245), -1)
    cv2.rectangle(img, (x, y), (x + 150, y + 200), colour, -1)
    for i in range(4):
        cv2.putText(img, "MEDICINE 10 MG", (x + 158, y + 40 + i * 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
    if code:
        small = render_datamatrix(code, 4)
        img[y + 192 - small.shape[0]:y + 192, x + 292 - small.shape[1]:x + 292] = small
    return (x, y, x + 300, y + 200)


def scene():
    """A pack with a code, a pack without one, and a sheet of paper that is not a pack."""
    img = table()
    with_code = put_pack(img, 150, 150, (200, 90, 40), ntin_element_string("654177", "281231", serial="SN1"))
    no_code = put_pack(img, 800, 200, (60, 160, 40))
    cv2.rectangle(img, (300, 700), (620, 940), (250, 250, 250), -1)
    for i in range(14):
        cv2.line(img, (320, 720 + i * 16), (600, 720 + i * 16), (175, 175, 175), 1)
    return img, with_code, no_code


def near(box, expected, tolerance=40):
    return all(abs(a - b) <= tolerance for a, b in zip(box, expected))


@pytest.fixture
def known(monkeypatch):
    medicines = {"654177": med("654177", "SINTROM 4 mg COMPRIMIDOS", ["ACENOCUMAROL"], "B01AA07")}
    monkeypatch.setattr(Resolver, "by_cn", lambda self, c: medicines.get("".join(ch for ch in c if ch.isdigit())[:6]))


def test_the_box_finder_reports_only_the_pack_without_a_code_and_stays_silent_on_a_white_table():
    img, with_code, no_code = scene()
    found = boxes.find_boxes(img)
    assert len(found) == 2 and any(near(b, with_code) for b in found) and any(near(b, no_code) for b in found)       # the paper is not a pack
    left = boxes.without_code(found, [d.bbox for d in decode.find_datamatrix(img)])
    assert len(left) == 1 and near(left[0], no_code)
    white = table((232, 234, 236))
    cv2.rectangle(white, (150, 150), (450, 350), (200, 90, 40), -1)
    for i in range(4):
        cv2.putText(white, "MEDICINE 10 MG", (160, 205 + i * 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    assert boxes.regions(white) and boxes.find_packs(white) == []          # seen, but on white it was wrong more often than right


def test_the_room_server_sends_each_stage_as_soon_as_it_is_ready_and_missing_codes_only_at_the_end(tmp_path, monkeypatch, known):
    spec = importlib.util.spec_from_file_location("serve_world", ROOT / "scripts" / "serve_world.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.chdir(tmp_path)
    spec.loader.exec_module(module)
    (tmp_path / "web").mkdir()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(module.Handler, directory=str(tmp_path / "web")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    computed, real = [], module.decode.scan_stages

    def counted(gray, passes=None):
        for stage in real(gray, passes):
            computed.append(1)
            yield stage
    monkeypatch.setattr(module.decode, "scan_stages", counted)
    img, _, no_code = scene()
    request = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/scan", data=cv2.imencode(".jpg", img)[1].tobytes(), method="POST",
                                     headers={"Content-Type": "image/jpeg", "X-Effects": "0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:
            first = json.loads(reply.readline())
            computed_then = len(computed)
            stages = [first] + [json.loads(x) for x in reply.read().decode().splitlines() if x]
    finally:
        httpd.shutdown()
    assert first["done"] is False and computed_then < len(stages)          # the first boxes are on screen before the last pass has run
    assert all(s["nocode"] == [] for s in stages[:-1]) and [c["status"] for c in stages[-1]["codes"]] == ["verified"]
    assert len(stages[-1]["nocode"]) == 1 and near(stages[-1]["nocode"][0], no_code) and stages[-1]["advice"]["text"]
    blurred, pack = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 4), {"bbox": (800, 200, 1100, 400), "side": 600}
    assert "blurry" in advice.advise(blurred, [pack], [], [pack["bbox"]])["text"]
    assert "blurry" not in advice.advise(blurred, [pack], [(150, 150, 450, 350)], [pack["bbox"]])["text"]      # codes are being read: blur is not the cause


def test_the_camera_server_listens_on_this_computer_only_and_keeps_only_real_pictures(tmp_path, monkeypatch, known):
    spec = importlib.util.spec_from_file_location("serve_camera", ROOT / "scripts" / "serve_camera.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.chdir(tmp_path)
    spec.loader.exec_module(module)
    local, lan = (module.make_server(0, directory=str(ROOT / "web"), lan=flag, https=False) for flag in (False, True))
    assert local.server_address[0] == "127.0.0.1" and lan.server_address[0] == "0.0.0.0"
    threading.Thread(target=local.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{local.server_address[1]}"

    def post(path, body):
        return urllib.request.urlopen(urllib.request.Request(url + path, data=body, method="POST", headers={"Content-Type": "image/jpeg"}), timeout=60)
    try:
        body = cv2.imencode(".jpg", synthetic.demo_photo([("654177", "281231")]))[1].tobytes()
        name = json.load(post("/photo", body))["saved"]
        folder = tmp_path / "data" / "camera_photos"
        assert (folder / name).read_bytes() == body == (folder / "latest.jpg").read_bytes()
        for path in ("/photo", "/scan"):
            with pytest.raises(urllib.error.HTTPError) as error:
                post(path, b"not a picture")
            assert error.value.code == 400
        assert len(list(folder.glob("photo_*.jpg"))) == 1
    finally:
        local.shutdown()
        lan.server_close()


def test_online_each_visitor_keeps_their_own_room_photos_and_there_is_no_camera_page(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    spec = importlib.util.spec_from_file_location("serve_world_public", ROOT / "scripts" / "serve_world.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.chdir(tmp_path)
    spec.loader.exec_module(module)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(module.Handler, directory=str(ROOT / "web")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    body = cv2.imencode(".jpg", synthetic.demo_photo([("654177", "281231")]))[1].tobytes()

    def photo(session):
        headers = {"Content-Type": "image/jpeg", **({"X-Session": session} if session else {})}
        return urllib.request.urlopen(urllib.request.Request(url + "/photo", data=body, method="POST", headers=headers), timeout=60)
    try:
        photo("visitor-0001")
        assert (tmp_path / "data" / "world_photos" / "visitor-0001" / "latest.jpg").read_bytes() == body
        assert not (tmp_path / "data" / "world_photos" / "latest.jpg").exists()                       # nothing shared between visitors
        for bad in ("", "../../etc"):
            with pytest.raises(urllib.error.HTTPError) as error:
                photo(bad)
            assert error.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url + "/camera.html", timeout=10)
        assert error.value.code == 404
        assert b"Not medical advice" in urllib.request.urlopen(url + "/", timeout=10).read()
    finally:
        httpd.shutdown()
