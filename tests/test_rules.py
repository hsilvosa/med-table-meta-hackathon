"""What the checks say: facts from CIMA (same ingredient, same group, expiry) and word-for-word leaflet quotes; never "safe", never a hidden gap."""

from datetime import date, timedelta

from fixtures import (
    ACENOCUMAROL,
    IBUPROFENO,
    LORAZEPAM,
    METFORMINA_850,
    NAPROXENO,
    OMEPRAZOL,
    PARACETAMOL_A,
    PARACETAMOL_B,
    SECTIONS,
    TODAY,
    FakeSmpc,
    offline,
    pack,
)

from medtable import smpc
from medtable.rules import check_packs, meal_notes
from medtable.smpc import Smpc


def test_same_ingredient_same_group_and_expiry_are_flagged():
    dup = [f for f in check_packs([pack(PARACETAMOL_A), pack(PARACETAMOL_B)], today=TODAY) if f.kind == "duplicate_ingredient"]
    assert len(dup) == 1 and set(dup[0].cns) == {"650001", "650002"}
    assert [f.kind for f in check_packs([pack(IBUPROFENO), pack(NAPROXENO)], today=TODAY)] == ["same_atc_class"]        # not a duplicate
    found = {f.kind: f for f in check_packs([pack(OMEPRAZOL, TODAY - timedelta(days=1)), pack(METFORMINA_850, TODAY + timedelta(days=10)),
                                             pack(ACENOCUMAROL, date(2030, 1, 1))], today=TODAY)}
    assert found["expired"].severity == "review" and found["expires_soon"].severity == "info" and len(found) == 2


def test_leaflet_quotes_are_exact_and_nothing_is_ever_called_safe(monkeypatch):
    mentions = [f for f in check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], FakeSmpc(), TODAY) if f.kind == "smpc_mention"]
    assert mentions and all(m.quote in SECTIONS[(IBUPROFENO.nregistro, "4.5")] for m in mentions)
    assert "not a full interaction check" in mentions[0].text()
    quiet = check_packs([pack(OMEPRAZOL), pack(METFORMINA_850)], FakeSmpc(), TODAY)       # "no relevant interactions described": quoted, not escalated
    assert [(f.kind, f.severity) for f in quiet] == [("smpc_mention", "info")]
    monkeypatch.setitem(SECTIONS, (IBUPROFENO.nregistro, "4.5"),
                        "No se han realizado estudios con otros farmacos, pero el acenocumarol aumenta el riesgo de hemorragia con este medicamento.")
    assert [f.severity for f in check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], FakeSmpc(), TODAY) if f.kind == "smpc_mention"] == ["review"]
    long_text = "Potencian el efecto: " + "alopurinol, androgenos, " * 15 + "paracetamol, " + "otros farmacos, " * 25 + "fin."
    (_, cut), = smpc.find_mentions(long_text, ["PARACETAMOL"])
    assert cut.endswith(smpc.CUT) and all(part in long_text for part in smpc.fragments(cut))      # a shortened quote is made of exact pieces


def test_a_leaflet_section_that_could_not_be_checked_is_said_so(tmp_path, monkeypatch):
    gap = check_packs([pack(IBUPROFENO), pack(LORAZEPAM)], FakeSmpc(), TODAY)           # no 4.5 text for lorazepam
    assert [f.cns[0] for f in gap if f.kind == "smpc_unavailable"] == ["700001"] and "was not done" in [f for f in gap if f.kind == "smpc_unavailable"][0].text()
    offline(monkeypatch)
    lost = check_packs([pack(OMEPRAZOL), pack(LORAZEPAM)], Smpc(tmp_path))
    assert "smpc_unavailable" in {f.kind for f in lost} and "smpc_mention" not in {f.kind for f in lost}
    assert check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], None, TODAY) == []        # leaflets turned off: only the facts run


def test_meal_notes_quote_section_4_2():
    found = meal_notes([pack(METFORMINA_850), pack(OMEPRAZOL), pack(ACENOCUMAROL)], FakeSmpc())
    notes = [f for f in found if f.kind == "meal_note"]
    assert [f.cns[0] for f in notes] == ["680001", "690001"] and [f.cns[0] for f in found if f.kind == "smpc_unavailable"] == ["670001"]
    assert "durante las comidas" in notes[0].quote and "decided by the caregiver" in notes[0].text()
