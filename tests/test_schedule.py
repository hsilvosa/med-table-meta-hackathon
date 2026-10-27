"""The medication sheet against the packs on the table."""

from fixtures import (PARACETAMOL_B, med, strength, IBUPROFENO, LORAZEPAM, METFORMINA_500, METFORMINA_850, OMEPRAZOL, PARACETAMOL_A, VALSARTAN_40,
                      VALSARTAN_HCT, pack)
from medtable import schedule
from medtable.schedule import Line, dose_number, lines_from_rows, reconcile


def row(text, d="0", c="0", n="0", a="0", obs="", **extra):
    return {"medicine": text, "breakfast": d, "lunch": c, "dinner": n, "bedtime": a, "remarks": obs, **extra}


def test_dose_parsing_accepts_only_known_shapes():
    assert [dose_number(x) for x in ("0", "1", "2", "0,5", "0.5", "1/2", "3/4", " 1 ")] == [0.0, 1.0, 2.0, 0.5, 0.5, 0.5, 0.75, 1.0]
    assert all(dose_number(x) is None for x in ("", "uno", "1-2", "1/0", "x", "100"))


def test_unreadable_doses_raise_findings_and_lines_start_unconfirmed():
    lines, findings = lines_from_rows([row("Lorazepam 1 mg", a="media"), row("Omeprazol 20 mg", d="1")])
    assert [f.kind for f in findings] == ["invalid_dose"] and findings[0].quote == "media"
    assert not any(line.confirmed for line in lines)


def test_strengths_are_compared_in_milligrams():
    assert schedule._numbers("Paracetamol 1 g comprimidos") == [1000.0]
    assert schedule._numbers("Valsartan/Hidroclorotiazida 160/12,5 mg") == [12.5, 160.0]
    assert schedule.strength_matches(Line("Paracetamol 1 g"), pack(PARACETAMOL_A)) is True
    assert schedule.strength_matches(Line("Metformina 500 mg"), pack(METFORMINA_850)) is False
    assert schedule.strength_matches(Line("Metformina"), pack(METFORMINA_850)) is None


def test_matching_by_ingredient_and_strength():
    lines = [Line("Metformina 850 mg comprimidos"), Line("Omeprazol 20 mg capsulas"), Line("Valsartan/Hidroclorotiazida 160/12,5 mg")]
    packs = [pack(METFORMINA_850), pack(OMEPRAZOL), pack(VALSARTAN_40), pack(VALSARTAN_HCT)]
    result = reconcile(lines, packs)
    assert [result.matches[i].medicine.cn for i in range(3)] == ["680001", "690001", "710001"]  # combination wins over valsartan alone
    assert [f.kind for f in result.findings] == ["not_prescribed"]  # the lone valsartan 40 mg pack is not on the sheet
    assert result.findings[0].cns == ["710002"]


def test_prescribed_but_not_on_the_table():
    result = reconcile([Line("Atorvastatina 20 mg")], [pack(OMEPRAZOL)])
    assert [f.kind for f in result.findings] == ["prescribed_not_found", "not_prescribed"]
    assert result.blocked == {0: "no pack on the table matches"}


def test_wrong_strength_blocks_the_line():
    result = reconcile([Line("Metformina 500 mg comprimidos")], [pack(METFORMINA_850)])
    assert [f.kind for f in result.findings] == ["strength_mismatch"] and 0 in result.blocked
    assert "does not match" in result.findings[0].text()


def test_the_line_picks_the_pack_whose_strength_agrees():
    result = reconcile([Line("Metformina 500 mg")], [pack(METFORMINA_850), pack(METFORMINA_500)])
    assert result.matches[0].medicine.cn == "680002" and not result.blocked


def test_ambiguity_is_asked_not_guessed():
    result = reconcile([Line("Metformina")], [pack(METFORMINA_850), pack(METFORMINA_500)])
    assert [f.kind for f in result.findings] == ["ambiguous_match"] and 0 in result.blocked


def test_a_typed_cn_selects_the_pack_exactly():
    result = reconcile([Line("el de la mañana", cn="6800027")], [pack(METFORMINA_850), pack(METFORMINA_500)])
    assert result.matches[0].medicine.cn == "680002"


def test_a_laboratory_or_brand_word_in_the_line_breaks_a_tie_between_equal_ingredients():
    packs = [pack(PARACETAMOL_A), pack(PARACETAMOL_B)]  # "PARACETAMOL ALFA 1 g" and "TERMALGIN 1 g"
    assert reconcile([Line("Paracetamol Alfa 1 g")], packs).matches[0].medicine.cn == "650001"
    assert reconcile([Line("Termalgin 1 g")], packs).matches[0].medicine.cn == "650002"
    tie = reconcile([Line("Paracetamol 1 g")], packs)
    assert tie.matches == {} and [f.kind for f in tie.findings][0] == "ambiguous_match"  # no extra word: still asked, never guessed


def test_a_line_naming_only_one_of_the_packs_ingredients_is_not_that_pack():
    # "Valsartan" is not "Valsartan/Hidroclorotiazida": the table has a different medicine than the sheet lists
    result = reconcile([Line("Valsartan"), Line("Valsartan 160 mg")], [pack(VALSARTAN_HCT)])
    assert result.matches == {} and [f.kind for f in result.findings].count("prescribed_not_found") == 2
    assert [f.kind for f in result.findings].count("not_prescribed") == 1
    both = reconcile([Line("Valsartan/Hidroclorotiazida 160/12,5 mg")], [pack(VALSARTAN_HCT), pack(VALSARTAN_40)])
    assert both.matches[0].medicine.cn == "710001"
    alone = reconcile([Line("Valsartan 40 mg")], [pack(VALSARTAN_HCT), pack(VALSARTAN_40)])
    assert alone.matches[0].medicine.cn == "710002"


def test_brand_names_match_through_the_first_word():
    result = reconcile([Line("Ibuprofeno BETA")], [pack(IBUPROFENO), pack(LORAZEPAM)])
    assert result.matches[0].medicine.cn == "660001"


def test_liquid_forms_are_not_compared_because_cima_lists_the_amount_per_container():
    syrup = med("720001", "IBUPROFENO CINFA 20 MG/ML SUSPENSION ORAL", ["IBUPROFENO"], "M01AE01", strengths=strength(("2.0", "g")), form="SUSPENSION ORAL")
    assert schedule.strength_matches(Line("IBUPROFENO CINFA 20 MG/ML SUSPENSION ORAL"), pack(syrup)) is None
    assert reconcile([Line("Ibuprofeno 20 mg/ml")], [pack(syrup)]).blocked == {}
