"""When the official database cannot be reached: nothing is verified by guess, the caregiver is told, and the app does not hang or crash."""

import urllib.error

import pytest

from fixtures import LORAZEPAM, OMEPRAZOL, pack
from helpers import ntin_element_string
from medtable import cima, decode, identify, rules
from medtable.pipeline import manual_pack
from medtable.resolve import Resolver
from medtable.smpc import Smpc


def offline(monkeypatch):
    def no_network(request, timeout=None):
        raise urllib.error.URLError("no route to host")
    monkeypatch.setattr(cima.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(cima.time, "sleep", lambda s: None)


def test_a_failed_fetch_is_reported_as_unreachable_after_the_retries(monkeypatch):
    offline(monkeypatch)
    with pytest.raises(cima.Unreachable):
        cima.fetch("https://cima.aemps.es/x", retries=2)


def test_a_code_read_while_offline_is_unverified_with_a_plain_reason(tmp_path, monkeypatch):
    offline(monkeypatch)
    reading = identify.read_code(decode.Detection(ntin_element_string("848226"), (0, 0, 10, 10), "zxing"), Resolver(tmp_path))
    assert reading.status == "unverified" and reading.medicine is None
    assert reading.problems == [identify.UNREACHABLE]


def test_a_typed_code_while_offline_says_so(tmp_path, monkeypatch):
    offline(monkeypatch)
    found, problem = manual_pack("8482269", Resolver(tmp_path))
    assert found is None and "could not be reached" in problem


def test_leaflet_sections_that_cannot_be_fetched_are_reported_as_not_checked(tmp_path, monkeypatch):
    offline(monkeypatch)
    findings = rules.check_packs([pack(OMEPRAZOL), pack(LORAZEPAM)], Smpc(tmp_path))
    assert {f.kind for f in findings} >= {"smpc_unavailable"}
    assert not any(f.kind == "smpc_mention" for f in findings)
