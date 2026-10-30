"""Codes and the official database: a pack is verified only when its code proves it, and nothing is ever guessed."""

import urllib.error
from datetime import date

import cv2
import numpy as np
import zxingcpp
from fixtures import ntin_element_string, offline, render_datamatrix

from medtable import cima, cn, decode, gs1, identify, synthetic
from medtable.resolve import Resolver
from medtable.smpc import Smpc

AZOPT = {
    "nregistro": "00129001", "nombre": "AZOPT 10 mg/ml COLIRIO EN SUSPENSION", "labtitular": "Novartis Europharm Limited",
    "comerc": True, "formaFarmaceutica": {"nombre": "COLIRIO EN SUSPENSION"},
    "principiosActivos": [{"nombre": "BRINZOLAMIDA"}],
    "atcs": [{"codigo": "S01EC04", "nombre": "Brinzolamida", "nivel": 5}],
    "presentaciones": [{"cn": "848226", "nombre": "AZOPT 10 mg/ml COLIRIO EN SUSPENSION, 1 frasco de 5 ml"}],
    "fotos": [], "docs": [],
}


def fake_cima(monkeypatch, answer=AZOPT):
    calls = []

    def medicine_by_cn(cn6):
        calls.append(cn6)
        if cn6 != "848226":
            raise urllib.error.HTTPError("u", 404, "not found", {}, None)
        return answer
    monkeypatch.setattr(cima, "medicine_by_cn", medicine_by_cn)
    return calls


def test_check_digits_and_gs1_parsing():
    for cn6, digit in [("725702", 8), ("698809", 1), ("682811", 3), ("672339", 5), ("848226", 9)]:      # read from real CIMA pack photos
        assert cn.check_digit(cn6) == digit and cn.is_valid(f"{cn6}.{digit}")
    assert not cn.is_valid("7257020") and cn.find_cn("C.N. 725702.8 O") == "7257028" and cn.find_cn("lote 123") is None
    code = gs1.parse_pack_code(ntin_element_string("848226"))
    assert (code.gtin, code.expiry, code.lot, code.serial, code.national.cn) == ("08470008482269", date(2028, 12, 31), "LOT123", "SN0001", "8482269")
    raw = "010847000848226917281231" + "10LOT123" + gs1.GS + "21SN0001"
    assert gs1.parse_elements("]d2" + raw) == gs1.parse_elements(raw.replace(gs1.GS, "<GS>")) == {"01": "08470008482269", "17": "281231", "10": "LOT123", "21": "SN0001"}
    assert gs1.parse_expiry("280200") == date(2028, 2, 29)                  # day 00 = end of the month


def test_a_code_never_gives_a_national_code_it_cannot_prove():
    bad_digit = gs1.national_code(gs1.parse_elements("(01)08470008482260(17)281231"))       # the last digit should be 9
    assert bad_digit.cn is None and bad_digit.problems
    ntin = f"0{cn.gtin13('680001')}"
    disagree = gs1.national_code(gs1.parse_elements(f"(01){ntin}(712)700001{cn.check_digit('700001')}"))
    assert disagree.cn is None and "contradicts itself" in disagree.problems[0]
    month_13 = gs1.parse_pack_code(f"(01){ntin}(17)261399")
    assert month_13.expiry is None and any("expiry field (17)" in p for p in month_13.national.problems)


def test_a_photo_gives_verified_expired_and_unknown_packs(tmp_path, monkeypatch):
    fake_cima(monkeypatch)
    canvas = np.full((900, 1400, 3), 200, np.uint8)
    known, unknown = ntin_element_string("848226", expiry="260100"), ntin_element_string("725702", serial="SN0002")     # expired January 2026; valid CN not in CIMA
    for text, (x, y) in ((known, (100, 120)), (unknown, (900, 560))):
        code = render_datamatrix(text, module_px=7)
        canvas[y:y + code.shape[0], x:x + code.shape[1]] = code
    readings = {r.raw: r for r in identify.identify(canvas, Resolver(tmp_path), today=date(2026, 10, 26))}
    assert readings[known].status == "verified" and readings[known].expired is True and readings[known].medicine.name.startswith("AZOPT")
    assert readings[unknown].status == "unverified" and readings[unknown].medicine is None and "CIMA has no medicine" in readings[unknown].problems[0]


def test_cima_must_list_the_scanned_code_and_an_empty_answer_means_unknown(tmp_path, monkeypatch):
    calls = fake_cima(monkeypatch)
    resolver = Resolver(tmp_path / "a")
    assert resolver.by_cn("8482269").presentation.endswith("1 frasco de 5 ml") and resolver.by_cn("848226") and calls == ["848226"]      # cached
    fake_cima(monkeypatch, {**AZOPT, "presentaciones": [{"cn": "111111", "nombre": "otra presentacion"}]})
    other = identify.read_code(decode.Detection(ntin_element_string("848226"), (0, 0, 1, 1), "zxing"), Resolver(tmp_path / "b"))
    assert other.status == "unverified" and "does not list CN 848226" in other.problems[-1]
    monkeypatch.setattr(cima, "fetch", lambda url, **kw: b"")              # the real API answers an unknown code with HTTP 200 and an empty body
    assert Resolver(tmp_path / "c").by_cn("123450") is None


def test_offline_a_code_stays_unverified_and_the_demo_still_works_from_the_shipped_data(tmp_path, monkeypatch):
    offline(monkeypatch)
    reading = identify.read_code(decode.Detection(ntin_element_string("848226"), (0, 0, 10, 10), "zxing"), Resolver(tmp_path))
    assert reading.status == "unverified" and reading.problems == [identify.UNREACHABLE]
    items = [("654177", "281231"), ("662025", "270430"), ("715240", "250600"), ("677379", "280131"), ("656012", "271130"), ("100008", "281231")]
    readings = identify.identify(synthetic.demo_photo(items), Resolver(tmp_path))         # empty cache, no network: only demo_cache/
    assert sorted(r.medicine.cn for r in readings if r.status == "verified") == ["654177", "656012", "662025", "677379", "715240"]
    assert [r.problems for r in readings if r.status != "verified"] == [["CIMA has no medicine with CN 100008"]]      # known unknown, not "no connection"
    assert Smpc(tmp_path).section("58994", "4.5").text


def small_code_photo(text, px_per_module, angle, seed):
    """A code of `px_per_module` pixels per module, turned and blurred, on a busy background (a 12 MP phone at 90 cm is about 1.9)."""
    rng = np.random.default_rng(seed)
    base = render_datamatrix(text, module_px=16, quiet=2)
    small = cv2.resize(base, None, fx=px_per_module / 16, fy=px_per_module / 16, interpolation=cv2.INTER_AREA)
    background = (150 + 40 * cv2.GaussianBlur(rng.random((900, 1200)).astype(np.float32), (0, 0), 25) / 0.05).clip(60, 220)
    img = cv2.cvtColor(background.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    side = int(np.hypot(*small.shape[:2])) + 2
    top, left = (side - small.shape[0]) // 2, (side - small.shape[1]) // 2
    padded = cv2.copyMakeBorder(small, top, side - small.shape[0] - top, left, side - small.shape[1] - left, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    turned = cv2.warpAffine(padded, cv2.getRotationMatrix2D((side / 2, side / 2), angle, 1.0), (side, side), borderValue=(255, 255, 255))
    img[300:300 + side, 400:400 + side] = turned
    img = cv2.GaussianBlur(img, (0, 0), 0.9)
    return np.clip(img.astype(np.float32) + rng.normal(0, 3.0, img.shape), 0, 255).astype(np.uint8)


def test_small_turned_codes_are_read_and_nothing_is_invented_below_the_limit():
    text = ntin_element_string("662025", "281231", "L1", "SN0001")
    img = small_code_photo(text, 1.9, 33, 3)
    plain = {r.text for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.DataMatrix, text_mode=zxingcpp.TextMode.HRI)}
    assert text not in plain                                                # the test means something: a plain read fails
    assert [d.text for d in decode.find_datamatrix(img)] == [text]
    assert decode.find_datamatrix(small_code_photo(text, 0.8, 10, 8)) == []        # a miss is acceptable, a wrong code never is
    noise = cv2.GaussianBlur(np.random.default_rng(9).random((900, 1200, 3)).astype(np.float32), (0, 0), 1.2)
    assert decode.find_datamatrix((255 * (noise - noise.min()) / np.ptp(noise)).astype(np.uint8)) == []
