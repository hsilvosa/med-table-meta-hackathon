"""Duplicates, class overlap, expiry and SmPC 4.5 quotations."""

from datetime import date, timedelta

from fixtures import (ACENOCUMAROL, FakeSmpc, IBUPROFENO, METFORMINA_850, NAPROXENO, OMEPRAZOL, PARACETAMOL_A,
                      PARACETAMOL_B, SECTIONS, TODAY, pack)
from medtable import smpc
from medtable.rules import check_packs, meal_notes


def kinds(findings):
    return [f.kind for f in findings]


def test_two_brands_of_the_same_ingredient_are_flagged_as_duplicates():
    found = check_packs([pack(PARACETAMOL_A), pack(PARACETAMOL_B)], today=TODAY)
    dup = [f for f in found if f.kind == "duplicate_ingredient"]
    assert len(dup) == 1 and set(dup[0].cns) == {"650001", "650002"}
    assert "same active ingredient" in dup[0].text()


def test_same_class_but_different_ingredient_is_a_class_finding_not_a_duplicate():
    found = check_packs([pack(IBUPROFENO), pack(NAPROXENO)], today=TODAY)
    assert kinds(found) == ["same_atc_class"]
    assert "M01AE" in found[0].detail


def test_expired_and_expiring_packs():
    found = check_packs([pack(OMEPRAZOL, TODAY - timedelta(days=1)), pack(METFORMINA_850, TODAY + timedelta(days=10)),
                         pack(ACENOCUMAROL, date(2030, 1, 1))], today=TODAY)
    by_kind = {f.kind: f for f in found}
    assert by_kind["expired"].severity == "review" and by_kind["expired"].detail == "2026-10-25"
    assert by_kind["expires_soon"].severity == "info"
    assert len(found) == 2


def test_smpc_mention_quotes_the_source_verbatim_and_names_the_other_pack():
    found = check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], FakeSmpc(), TODAY)
    mentions = [f for f in found if f.kind == "smpc_mention"]
    assert mentions
    text = SECTIONS[(IBUPROFENO.nregistro, "4.5")]
    assert all(m.quote in text for m in mentions)  # exact substrings of the source
    assert all(m.names == [IBUPROFENO.name, ACENOCUMAROL.name] for m in mentions)
    assert "acenocumarol" in mentions[0].quote.lower()
    assert "not a full interaction check" in mentions[0].text()


def test_no_mention_is_not_reported_as_safe():
    found = check_packs([pack(OMEPRAZOL), pack(METFORMINA_850)], FakeSmpc(), TODAY)
    # omeprazol's text does name 'metformina': that is quoted, and it is the only finding; nothing says "no interactions"
    assert kinds(found) == ["smpc_mention"]
    assert "metformina" in found[0].quote.lower()
    assert found[0].severity == "info"  # the sentence says nothing was described: quoted, not escalated


def test_without_a_smpc_source_only_the_deterministic_checks_run():
    found = check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], None, TODAY)
    assert found == []


def test_meal_notes_quote_section_4_2_sentences_about_food():
    found = meal_notes([pack(METFORMINA_850), pack(OMEPRAZOL), pack(ACENOCUMAROL)], FakeSmpc())
    assert [(f.kind, f.severity, f.cns[0]) for f in found if f.kind == "meal_note"] == [("meal_note", "info", "680001"), ("meal_note", "info", "690001")]
    assert [f.cns[0] for f in found if f.kind == "smpc_unavailable"] == ["670001"]
    found = [f for f in found if f.kind == "meal_note"]
    assert "durante las comidas" in found[0].quote and "con o sin alimentos" in found[1].quote
    assert all(f.quote in SECTIONS[(f.source and (METFORMINA_850 if f.cns[0] == "680001" else OMEPRAZOL).nregistro, "4.2")] for f in found)
    assert "decided by the caregiver" in found[0].text()


def test_a_cut_quote_ends_with_the_marker_and_a_complete_sentence_does_not():
    long_text = "Los siguientes medicamentos potencian el efecto: " + "alopurinol, esteroides anabolizantes, androgenos, " * 12 + "paracetamol, ketoconazol, " + "otros farmacos distintos, " * 20 + "fin."
    (_, cut), = smpc.find_mentions(long_text, ["PARACETAMOL"])
    assert cut.endswith(smpc.CUT) and all(part in long_text for part in smpc.fragments(cut))
    (_, whole), = smpc.find_mentions("Anticoagulantes orales (acenocumarol, warfarina): posible potenciacion del efecto anticoagulante.", ["ACENOCUMAROL"])
    assert not whole.endswith(smpc.CUT)
