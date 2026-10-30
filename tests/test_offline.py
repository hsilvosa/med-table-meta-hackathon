"""When the official database cannot be reached: nothing is verified by guess, the caregiver is told, and the app does not hang or crash."""

import urllib.error


from fixtures import LORAZEPAM, OMEPRAZOL, pack
from helpers import ntin_element_string
from medtable import cima, decode, identify, rules
from medtable.resolve import Resolver
from medtable.smpc import Smpc


def offline(monkeypatch):
    def no_network(request, timeout=None):
        raise urllib.error.URLError("no route to host")
    monkeypatch.setattr(cima.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(cima.time, "sleep", lambda s: None)


def test_a_code_read_while_offline_is_unverified_with_a_plain_reason(tmp_path, monkeypatch):
    offline(monkeypatch)
    reading = identify.read_code(decode.Detection(ntin_element_string("848226"), (0, 0, 10, 10), "zxing"), Resolver(tmp_path))
    assert reading.status == "unverified" and reading.medicine is None
    assert reading.problems == [identify.UNREACHABLE]


def test_leaflet_sections_that_cannot_be_fetched_are_reported_as_not_checked(tmp_path, monkeypatch):
    offline(monkeypatch)
    findings = rules.check_packs([pack(OMEPRAZOL), pack(LORAZEPAM)], Smpc(tmp_path))
    assert {f.kind for f in findings} >= {"smpc_unavailable"}
    assert not any(f.kind == "smpc_mention" for f in findings)


def test_the_demo_photo_is_read_with_no_connection_from_the_data_shipped_in_the_repository(tmp_path, monkeypatch):
    from medtable import synthetic
    offline(monkeypatch)
    items = [("654177", "281231"), ("662025", "270430"), ("715240", "250600"), ("677379", "280131"), ("656012", "271130"), ("100008", "281231")]
    readings = identify.identify(synthetic.demo_photo(items), Resolver(tmp_path))         # an empty cache: only demo_cache/ and no network
    assert sorted(r.medicine.cn for r in readings if r.status == "verified") == ["654177", "656012", "662025", "677379", "715240"]
    unknown = [r for r in readings if r.status != "verified"]
    assert len(unknown) == 1 and unknown[0].problems == ["CIMA has no medicine with CN 100008"]       # known to be unknown, not "no connection"
    assert Smpc(tmp_path).section("58994", "4.5").text                     # the leaflet quotes too
