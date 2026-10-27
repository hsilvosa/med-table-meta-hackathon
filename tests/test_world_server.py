"""The photo server of the 3D room: saves a photo with its ground truth and the 'latest' copy, and applies the phone effects."""

import json
import urllib.error
import threading
import urllib.parse
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import cv2
import numpy as np
import pytest

from fixtures import med
from medtable import synthetic
from medtable.resolve import Resolver



@pytest.fixture
def server(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("serve_world", "scripts/serve_world.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(".")
    spec.loader.exec_module(module)
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<html>room</html>")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(module.Handler, directory=str(tmp_path / "web")))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield module, f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def post(url, jpeg, truth, effects):
    request = urllib.request.Request(url + "/photo", data=jpeg, method="POST", headers={
        "Content-Type": "image/jpeg", "X-Truth": urllib.parse.quote(json.dumps(truth)), "X-Effects": "1" if effects else "0"})
    with urllib.request.urlopen(request, timeout=20) as reply:
        return json.load(reply)


def jpeg_of_demo_code():
    ok, buffer = cv2.imencode(".jpg", synthetic.demo_photo([("654177", "281231")]))
    assert ok
    return buffer.tobytes()


def test_a_photo_is_saved_with_its_truth_and_as_latest(server):
    module, url, tmp = server
    truth = {"labels": [{"cn7": "6541777"}], "table": "mesa1", "pose": {"x": 0.1}}
    saved = post(url, jpeg_of_demo_code(), truth, effects=False)
    folder = tmp / "data" / "world_photos"
    assert (folder / saved["name"]).exists() and (folder / "latest.jpg").read_bytes() == (folder / saved["name"]).read_bytes()
    assert json.loads((folder / "latest.json").read_text(encoding="utf-8")) == truth
    assert (folder / saved["name"]).read_bytes() == jpeg_of_demo_code()  # no effects: stored untouched


def test_phone_effects_change_the_pixels_but_keep_the_code_readable(server):
    module, url, tmp = server
    saved = post(url, jpeg_of_demo_code(), {}, effects=True)
    stored = cv2.imread(str(tmp / "data" / "world_photos" / saved["name"]))
    original = synthetic.demo_photo([("654177", "281231")])
    assert stored.shape == original.shape and np.abs(stored.astype(int) - original.astype(int)).mean() > 0.5
    from medtable import decode
    assert [d.text for d in decode.find_datamatrix(stored)] == [d.text for d in decode.find_datamatrix(original)]


def test_only_the_photo_endpoint_accepts_posts_and_modules_are_served_as_javascript(server):
    module, url, _ = server
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(urllib.request.Request(url + "/other", data=b"x", method="POST"), timeout=10)
    assert error.value.code == 404
    assert urllib.request.urlopen(url + "/", timeout=10).read() == b"<html>room</html>"
    import mimetypes
    assert mimetypes.guess_type("main.js")[0] == "text/javascript"


def scan(url, jpeg, effects=False):
    request = urllib.request.Request(url + "/scan", data=jpeg, method="POST", headers={"Content-Type": "image/jpeg", "X-Effects": "1" if effects else "0"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        return json.load(reply)


def jpeg_of(items):
    ok, buffer = cv2.imencode(".jpg", synthetic.demo_photo(items))
    assert ok
    return buffer.tobytes()


@pytest.fixture
def cima(monkeypatch):
    known = {"654177": med("654177", "SINTROM 4 mg COMPRIMIDOS", ["ACENOCUMAROL"], "B01AA07")}
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: known.get("".join(c for c in cn if c.isdigit())[:6]))


def test_live_scan_reports_where_each_code_is_and_whether_it_is_verified(server, cima):
    module, url, tmp = server
    reply = scan(url, jpeg_of([("654177", "281231"), ("662025", "270430")]))        # the second code is valid but CIMA (here) does not know it
    width, height = reply["size"]
    by_status = {c["status"]: c for c in reply["codes"]}
    assert sorted(by_status) == ["unverified", "verified"]
    assert by_status["verified"]["name"] == "SINTROM 4 mg COMPRIMIDOS" and by_status["verified"]["expired"] is False
    assert by_status["unverified"]["name"] is None and "CIMA has no medicine" in by_status["unverified"]["problem"]
    for code in reply["codes"]:
        x0, y0, x1, y1 = code["bbox"]
        assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height
    assert not (tmp / "data" / "world_photos").exists()        # a preview frame is never saved: only a photo is


def test_live_scan_of_a_frame_without_codes_and_of_something_that_is_not_an_image(server, cima):
    module, url, _ = server
    ok, blank = cv2.imencode(".jpg", np.full((300, 400, 3), 200, np.uint8))
    assert scan(url, blank.tobytes())["codes"] == []
    with pytest.raises(urllib.error.HTTPError) as error:
        scan(url, b"this is not a jpeg")
    assert error.value.code == 400


def test_live_scan_works_on_a_frame_with_the_phone_effects(server, cima):
    module, url, _ = server
    reply = scan(url, jpeg_of([("654177", "281231")]), effects=True)
    assert [c["status"] for c in reply["codes"]] == ["verified"]
