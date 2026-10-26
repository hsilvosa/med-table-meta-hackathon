"""Duplicates, class overlap, expiry and SmPC 4.5 quotations."""

from datetime import date, timedelta

from fixtures import (ACENOCUMAROL, FakeSmpc, IBUPROFENO, METFORMINA_850, NAPROXENO, OMEPRAZOL, PARACETAMOL_A,
                      PARACETAMOL_B, SECTIONS, TODAY, VALSARTAN_40, VALSARTAN_HCT, pack)
from medtable import smpc
from medtable.rules import check_packs


def kinds(findings):
    return [f.kind for f in findings]


def test_two_brands_of_the_same_ingredient_are_flagged_as_duplicates():
    found = check_packs([pack(PARACETAMOL_A), pack(PARACETAMOL_B)], today=TODAY)
    dup = [f for f in found if f.kind == "duplicate_ingredient"]
    assert len(dup) == 1 and set(dup[0].cns) == {"650001", "650002"}
    assert "mismo principio activo" in dup[0].text("es") and "same active ingredient" in dup[0].text("en")


def test_same_class_but_different_ingredient_is_a_class_finding_not_a_duplicate():
    found = check_packs([pack(IBUPROFENO), pack(NAPROXENO)], today=TODAY)
    assert kinds(found) == ["same_atc_class"]
    assert "M01AE" in found[0].detail


def test_unrelated_medicines_raise_nothing():
    assert check_packs([pack(METFORMINA_850), pack(ACENOCUMAROL)], FakeSmpc(), TODAY) == []


def test_partial_overlap_valsartan_alone_and_in_combination():
    found = check_packs([pack(VALSARTAN_40), pack(VALSARTAN_HCT)], today=TODAY)
    assert "duplicate_ingredient" in kinds(found)  # shares valsartan even though the ATC codes differ


def test_expired_and_expiring_packs():
    found = check_packs([pack(OMEPRAZOL, TODAY - timedelta(days=1)), pack(METFORMINA_850, TODAY + timedelta(days=10)),
                         pack(ACENOCUMAROL, date(2030, 1, 1))], today=TODAY)
    by_kind = {f.kind: f for f in found}
    assert by_kind["expired"].severity == "review" and by_kind["expired"].detail == "2026-10-25"
    assert by_kind["expires_soon"].severity == "info"
    assert len(found) == 2


def test_two_packs_of_one_medicine_is_info():
    found = check_packs([pack(OMEPRAZOL), pack(OMEPRAZOL)], today=TODAY)
    assert [(f.kind, f.severity) for f in found] == [("same_medicine_twice", "info")]


def test_smpc_mention_quotes_the_source_verbatim_and_names_the_other_pack():
    found = check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], FakeSmpc(), TODAY)
    mentions = [f for f in found if f.kind == "smpc_mention"]
    assert mentions
    text = SECTIONS[(IBUPROFENO.nregistro, "4.5")]
    assert all(m.quote in text for m in mentions)  # exact substrings of the source
    assert all(m.names == [IBUPROFENO.name, ACENOCUMAROL.name] for m in mentions)
    assert "acenocumarol" in mentions[0].quote.lower()
    assert "no es una comprobación completa" in mentions[0].text("es")


def test_no_mention_is_not_reported_as_safe():
    found = check_packs([pack(OMEPRAZOL), pack(METFORMINA_850)], FakeSmpc(), TODAY)
    # omeprazol's text does name 'metformina': that is quoted, and it is the only finding; nothing says "no interactions"
    assert kinds(found) == ["smpc_mention"]
    assert "metformina" in found[0].quote.lower()


def test_class_name_mentions_use_plural_and_accent_insensitive_matching():
    text = "Los inhibidores de la bomba de protones no modifican la absorción. Otra frase sin relación con el asunto en cuestión."
    assert smpc.find_mentions(text, ["INHIBIDOR DE LA BOMBA DE PROTONES"])
    assert not smpc.find_mentions(text, ["metformina"])


def test_without_a_smpc_source_only_the_deterministic_checks_run():
    found = check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], None, TODAY)
    assert found == []
