"""Decoding, resolving and identifying, with the network replaced by a stored CIMA response."""

import json
from datetime import date

import cv2
import numpy as np

from helpers import ntin_element_string, render_datamatrix
from medtable import cima, decode, identify
from medtable.resolve import Resolver

AZOPT = {
    "nregistro": "00129001", "nombre": "AZOPT 10 mg/ml COLIRIO EN SUSPENSION", "labtitular": "Novartis Europharm Limited",
    "comerc": True, "formaFarmaceutica": {"nombre": "COLIRIO EN SUSPENSION"},
    "principiosActivos": [{"nombre": "BRINZOLAMIDA"}],
    "atcs": [{"codigo": "S01EC04", "nombre": "Brinzolamida", "nivel": 5}],
    "presentaciones": [{"cn": "848226", "nombre": "AZOPT 10 mg/ml COLIRIO EN SUSPENSION, 1 frasco de 5 ml"}],
    "fotos": [{"tipo": "materialas", "url": "https://cima.aemps.es/cima/fotos/thumbnails/materialas/00129001/x.jpg"}],
    "docs": [{"tipo": 1, "urlHtml": "https://cima.aemps.es/cima/dochtml/ft/00129001/FT_00129001.html"}],
}


def fake_cima(monkeypatch, calls):
    def medicine_by_cn(cn6):
        calls.append(cn6)
        if cn6 != "848226":
            raise cima.urllib.error.HTTPError("u", 404, "not found", {}, None)
        return AZOPT
    monkeypatch.setattr(cima, "medicine_by_cn", medicine_by_cn)


def test_decode_round_trip_and_two_codes_in_one_photo():
    one, two = ntin_element_string("848226"), ntin_element_string("725702", serial="SN0002")
    canvas = np.full((900, 1400, 3), 200, np.uint8)
    for text, (x, y) in ((one, (100, 120)), (two, (900, 560))):
        code = render_datamatrix(text, module_px=7)
        canvas[y:y + code.shape[0], x:x + code.shape[1]] = code
    found = decode.find_datamatrix(canvas)
    assert {d.text for d in found} == {one, two}


def test_resolver_caches_and_reports_unknown(tmp_path, monkeypatch):
    calls: list[str] = []
    fake_cima(monkeypatch, calls)
    resolver = Resolver(tmp_path)
    medicine = resolver.by_cn("8482269")  # the check digit is ignored
    assert medicine and medicine.nregistro == "00129001" and medicine.atc_code(5) == "S01EC04"
    assert medicine.presentation.endswith("1 frasco de 5 ml")
    assert "00129001" in medicine.citation()
    assert resolver.by_cn("848226").name == medicine.name
    assert calls == ["848226"]  # second lookup came from the cache
    assert resolver.by_cn("999999") is None


def test_identify_marks_verified_expired_and_unknown(tmp_path, monkeypatch):
    fake_cima(monkeypatch, [])
    canvas = np.full((900, 1400, 3), 200, np.uint8)
    codes = {
        "known": (ntin_element_string("848226", expiry="260100"), (100, 120)),   # expired in January 2026
        "unknown": (ntin_element_string("725702", serial="SN0002"), (900, 560)),  # valid CN, not in the fake CIMA
    }
    for text, (x, y) in codes.values():
        code = render_datamatrix(text, module_px=7)
        canvas[y:y + code.shape[0], x:x + code.shape[1]] = code
    readings = {r.raw: r for r in identify.identify(canvas, Resolver(tmp_path), today=date(2026, 10, 26))}
    known = readings[codes["known"][0]]
    assert known.status == "verified" and known.expired is True and known.medicine.name.startswith("AZOPT")
    unknown = readings[codes["unknown"][0]]
    assert unknown.status == "unverified" and unknown.medicine is None and "CIMA has no medicine" in unknown.problems[0]


def test_non_code_text_is_unverified(tmp_path):
    reading = identify.read_code(decode.Detection("hello world", (0, 0, 1, 1), "zxing"), Resolver(tmp_path))
    assert reading.status == "unverified" and reading.problems


def test_cima_empty_body_for_an_unknown_cn_means_not_found(tmp_path, monkeypatch):
    """Observed on the real API: an unknown CN returns HTTP 200 with an empty body."""
    monkeypatch.setattr(cima, "fetch", lambda url, **kw: b"")
    assert Resolver(tmp_path).by_cn("123450") is None
