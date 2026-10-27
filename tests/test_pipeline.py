"""The whole flow without the UI: packs and sheet rows in, a plan out."""

from datetime import timedelta

from fixtures import FakeSmpc, IBUPROFENO, METFORMINA_850, OMEPRAZOL, TODAY
from medtable import cima
from medtable.identify import Reading
from medtable.pipeline import make_plan, manual_pack
from medtable.resolve import Resolver

from test_identify import AZOPT, fake_cima


def reading(medicine, expiry=None):
    return Reading("verified", (0, 0, 1, 1), "zxing", "raw", medicine.cn + "0", medicine, expiry, bool(expiry and expiry < TODAY))


def row(text, confirmed=True, **doses):
    return {"medicine": text, "breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "0", "remarks": "", "confirmed": confirmed, **doses}


def test_unverified_reading_is_listed_and_never_planned():
    bad = Reading("unverified", (0, 0, 1, 1), "zxing", "xyz", problems=["not a GS1 element string"])
    result = make_plan([reading(OMEPRAZOL), bad], [], [row("Omeprazol 20 mg", breakfast="1")], FakeSmpc(), TODAY)
    assert [e.name for e in result.plan.entries] == [OMEPRAZOL.name]
    assert ("the code read is not a GS1 medicine code", "could not be verified") in result.plan.not_included


def test_manual_pack_is_added_and_deduplicated_against_decoded_ones(tmp_path, monkeypatch):
    fake_cima(monkeypatch, [])
    pack, problem = manual_pack("C.N. 848226.9", Resolver(tmp_path))
    assert pack and not problem and pack.state == "confirmed" and pack.medicine.name.startswith("AZOPT")
    assert manual_pack("848226.0", Resolver(tmp_path))[1].startswith("The national code is not valid")
    assert "does not know" in manual_pack("7257028", Resolver(tmp_path))[1]
    result = make_plan([], [pack, pack], [row("Azopt", breakfast="1")], None, TODAY)
    assert len(result.packs) == 2 and len({p.medicine.cn for p in result.packs}) == 1


def test_end_to_end_with_findings_and_not_included():
    readings = [reading(METFORMINA_850), reading(IBUPROFENO), reading(OMEPRAZOL, TODAY - timedelta(days=1))]
    rows = [row("Metformina 850 mg", breakfast="1", dinner="1"), row("Omeprazol 20 mg", breakfast="1"), row("Ibuprofeno 600 mg", confirmed=False, lunch="1")]
    result = make_plan(readings, [], rows, FakeSmpc(), TODAY)
    assert [(e.slot, e.pack.medicine.cn) for e in result.plan.entries] == [("breakfast", "680001"), ("dinner", "680001")]
    reasons = dict(result.plan.not_included)
    assert "expired" in reasons["Omeprazol 20 mg"] and "has not confirmed" in reasons["Ibuprofeno 600 mg"]
    kinds = {f.kind for f in result.plan.findings}
    assert {"expired", "meal_note"} <= kinds
