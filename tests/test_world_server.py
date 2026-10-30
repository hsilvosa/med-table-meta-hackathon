"""The photo server of the 3D room: saves a photo with its ground truth and the 'latest' copy, and applies the phone effects."""

import json
import urllib.error
import threading
import urllib.parse
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import cv2
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


def scan_stages(url, jpeg, effects=False):
    """Every line the server sends for one frame: what was found so far after each stage."""
    request = urllib.request.Request(url + "/scan", data=jpeg, method="POST", headers={"Content-Type": "image/jpeg", "X-Effects": "1" if effects else "0"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        return [json.loads(line) for line in reply.read().decode().splitlines() if line]


def scan(url, jpeg, effects=False):
    return scan_stages(url, jpeg, effects)[-1]


def jpeg_of(items):
    ok, buffer = cv2.imencode(".jpg", synthetic.demo_photo(items))
    assert ok
    return buffer.tobytes()


@pytest.fixture
def cima(monkeypatch):
    known = {"654177": med("654177", "SINTROM 4 mg COMPRIMIDOS", ["ACENOCUMAROL"], "B01AA07")}
    monkeypatch.setattr(Resolver, "by_cn", lambda self, cn: known.get("".join(c for c in cn if c.isdigit())[:6]))


def test_live_scan_sends_each_stage_before_the_next_one_is_computed(server, cima, monkeypatch):
    module, url, _ = server
    computed = []
    real = module.decode.scan_stages

    def slow_stages(gray, passes=None):
        for stage in real(gray, passes):
            computed.append(len(computed))
            yield stage

    monkeypatch.setattr(module.decode, "scan_stages", slow_stages)
    request = urllib.request.Request(url + "/scan", data=jpeg_of([("654177", "281231")]), method="POST", headers={"Content-Type": "image/jpeg", "X-Effects": "0"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        first_line = reply.readline()
        seen_when_first_line_arrived = len(computed)
        reply.read()
    assert json.loads(first_line)["done"] is False
    assert seen_when_first_line_arrived < 1 + len(module.decode.LIVE_PASSES)      # the later passes had not run yet


def test_live_scan_reports_packs_with_no_code_read_only_in_the_last_stage(server, cima):
    from test_boxes import scene
    module, url, _ = server
    img, with_code, no_code = scene()
    ok, buffer = cv2.imencode(".jpg", img)
    stages = scan_stages(url, buffer.tobytes())
    assert all(s["nocode"] == [] for s in stages[:-1])                      # while it is still looking, nothing is said about missing codes
    last = stages[-1]
    assert last["done"] and [c["status"] for c in last["codes"]] == ["verified"]
    assert len(last["nocode"]) == 1
    x0, y0, x1, y1 = last["nocode"][0]
    assert abs(x0 - no_code[0]) < 40 and abs(y0 - no_code[1]) < 40 and abs(x1 - no_code[2]) < 40 and abs(y1 - no_code[3]) < 40
    assert all("advice" not in s for s in stages[:-1])                       # one sentence of advice, at the end only, and it never speaks of a medicine
    assert last["advice"]["level"] == "mid" and last["advice"]["text"] and last["advice"]["light"] in ("ok", "dark", "glare")    # the test scene is a white sheet: glare is a fair answer
