"""The whole flow without the UI: packs and sheet rows in, a plan out."""

from datetime import timedelta

from fixtures import FakeSmpc, IBUPROFENO, METFORMINA_850, OMEPRAZOL, TODAY
from medtable.identify import Reading
from medtable.pipeline import make_plan



def reading(medicine, expiry=None):
    return Reading("verified", (0, 0, 1, 1), "zxing", "raw", medicine.cn + "0", medicine, expiry, bool(expiry and expiry < TODAY))


def row(text, confirmed=True, **doses):
    return {"medicine": text, "breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "0", "remarks": "", "confirmed": confirmed, **doses}


def test_unverified_reading_is_listed_and_never_planned():
    bad = Reading("unverified", (0, 0, 1, 1), "zxing", "xyz", problems=["not a GS1 element string"])
    result = make_plan([reading(OMEPRAZOL), bad], [], [row("Omeprazol 20 mg", breakfast="1")], FakeSmpc(), TODAY)
    assert [e.name for e in result.plan.entries] == [OMEPRAZOL.name]
    assert ("the code read is not a GS1 medicine code", "could not be verified") in result.plan.not_included


def test_end_to_end_with_findings_and_not_included():
    readings = [reading(METFORMINA_850), reading(IBUPROFENO), reading(OMEPRAZOL, TODAY - timedelta(days=1))]
    rows = [row("Metformina 850 mg", breakfast="1", dinner="1"), row("Omeprazol 20 mg", breakfast="1"), row("Ibuprofeno 600 mg", confirmed=False, lunch="1")]
    result = make_plan(readings, [], rows, FakeSmpc(), TODAY)
    assert [(e.slot, e.pack.medicine.cn) for e in result.plan.entries] == [("breakfast", "680001"), ("dinner", "680001")]
    reasons = dict(result.plan.not_included)
    assert "expired" in reasons["Omeprazol 20 mg"] and "has not confirmed" in reasons["Ibuprofeno 600 mg"]
    kinds = {f.kind for f in result.plan.findings}
    assert {"expired", "meal_note"} <= kinds
