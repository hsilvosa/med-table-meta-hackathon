"""Regression tests for the findings of the adversarial review (each of these failed before the fix)."""

from datetime import date, timedelta

import pypdfium2 as pdfium
import pytest

from fixtures import (ACENOCUMAROL, FakeSmpc, IBUPROFENO, LORAZEPAM, METFORMINA_850, OMEPRAZOL, SECTIONS, TODAY, med, pack, strength)
from medtable.plan import NOT_CONFIRMED
from medtable import cn, gs1, sheet_reader
from medtable.calendar_pdf import render_pdf
from medtable.identify import Reading, read_code
from medtable.decode import Detection
from medtable.pipeline import make_plan
from medtable.plan import Entry, build_plan, to_ics
from medtable.resolve import Resolver
from medtable.rules import check_packs, mention_terms
from medtable.schedule import SLOTS, Line, reconcile


def row(text, confirmed=True, **doses):
    return {"medicine": text, "breakfast": "0", "lunch": "0", "dinner": "0", "bedtime": "0", "remarks": "", "confirmed": confirmed, **doses}


def reading(medicine, expiry=None):
    return Reading("verified", (0, 0, 1, 1), "zxing", "x", medicine.cn + "0", medicine, expiry)


def line(text, remarks="", **doses):
    return Line(text, {**dict.fromkeys(SLOTS, "0"), **doses}, remarks, confirmed=True)


def pdf_text(path):
    doc = pdfium.PdfDocument(str(path))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_two_lines_for_one_pack_never_both_reach_the_calendar():
    result = make_plan([reading(METFORMINA_850, date(2030, 1, 1))], [], [row("Metformina 850 mg", breakfast="1"), row("Metformina 850 mg", breakfast="1")], None, TODAY)
    assert result.plan.entries == []
    assert "pack_on_several_lines" in {f.kind for f in result.plan.findings}
    assert [why for _, why in result.plan.not_included] == ["the pack is on several lines; keep one"] * 2


def test_a_confirmed_line_with_all_zero_doses_is_reported():
    result = make_plan([reading(METFORMINA_850, date(2030, 1, 1))], [], [row("Metformina 850 mg")], None, TODAY)
    assert result.plan.entries == [] and "all_zero_line" in {f.kind for f in result.plan.findings}
    assert result.plan.not_included == [("Metformina 850 mg", "the line has no dose")]


def test_an_untouched_line_is_pending_not_a_problem():
    result = make_plan([reading(METFORMINA_850, date(2030, 1, 1))], [], [row("Metformina 850 mg", confirmed=False)], None, TODAY)
    assert "all_zero_line" not in {f.kind for f in result.plan.findings}
    assert result.plan.not_included == [("Metformina 850 mg", NOT_CONFIRMED)]


def test_unknown_expiry_is_reported_for_decoded_and_typed_packs():
    result = make_plan([reading(METFORMINA_850)], [pack(OMEPRAZOL, state="confirmed")], [], None, TODAY)
    by_cn = {f.cns[0]: f.severity for f in result.plan.findings if f.kind == "expiry_unknown"}
    assert by_cn == {"680001": "review", "690001": "info"}


def test_unreadable_expiry_field_is_a_problem_not_silence():
    code = gs1.parse_pack_code(f"(01)0{cn.gtin13('680001')}(17)261399")  # month 13
    assert code.expiry is None and any("expiry field (17)" in p for p in code.national.problems)


def test_ntin_and_712_that_disagree_give_no_cn():
    a, b = "680001", "700001"
    ntin = f"0{cn.gtin13(a)}"
    result = gs1.national_code(gs1.parse_elements(f"(01){ntin}(712){b}{cn.check_digit(b)}"))
    assert result.cn is None and "contradicts itself" in result.problems[0]
    agree = gs1.national_code(gs1.parse_elements(f"(01){ntin}(712){a}{cn.check_digit(a)}"))
    assert agree.cn == f"{a}{cn.check_digit(a)}"


def test_cima_answer_without_the_scanned_cn_among_its_presentations_does_not_verify(tmp_path, monkeypatch):
    from medtable import cima
    from test_identify import AZOPT
    other = {**AZOPT, "presentaciones": [{"cn": "111111", "nombre": "otra presentacion"}]}
    monkeypatch.setattr(cima, "medicine_by_cn", lambda cn6: other)
    from helpers import ntin_element_string
    reading_ = read_code(Detection(ntin_element_string("848226"), (0, 0, 1, 1), "zxing"), Resolver(tmp_path))
    assert reading_.status == "unverified" and "does not list CN 848226" in reading_.problems[-1]


def test_empty_or_missing_sheet_cells_are_reported():
    read = sheet_reader.rows_from_reply('[{"medicine": "Omeprazol 20 mg", "breakfast": "1", "lunch": ""}]')
    assert read.rows[0]["lunch"] == "0" and read.rows[0]["bedtime"] == "0"
    assert "empty or unread cell in lunch, dinner, bedtime" in read.problems[0]


def test_missing_smpc_sections_and_disabled_check_are_visible():
    gap = check_packs([pack(IBUPROFENO), pack(LORAZEPAM)], FakeSmpc(), TODAY)  # Lorazepam has no 4.5 text in the fixture
    assert [f.cns[0] for f in gap if f.kind == "smpc_unavailable"] == ["700001"]
    assert "was not done" in [f for f in gap if f.kind == "smpc_unavailable"][0].text()
    result = make_plan([reading(METFORMINA_850, date(2030, 1, 1))], [], [row("Metformina 850 mg", breakfast="1")], None, TODAY)
    assert result.plan.smpc_used is False


def test_pdf_states_when_the_smpc_check_did_not_run(tmp_path):
    rows = [row("Metformina 850 mg", breakfast="1")]
    off = make_plan([reading(METFORMINA_850, date(2030, 1, 1))], [], rows, None, TODAY).plan
    assert "were NOT consulted" in " ".join(pdf_text(render_pdf(off, tmp_path / "a.pdf")).split())
    on = make_plan([reading(METFORMINA_850, date(2030, 1, 1))], [], rows, FakeSmpc(), TODAY).plan
    assert "verbatim quotes from sections 4.2 and 4.5" in " ".join(pdf_text(render_pdf(on, tmp_path / "b.pdf")).split())


def test_a_negated_sentence_with_a_warning_cue_stays_at_review_level(monkeypatch):
    monkeypatch.setitem(SECTIONS, (IBUPROFENO.nregistro, "4.5"),
                        "No se han realizado estudios con otros farmacos, pero el acenocumarol aumenta el riesgo de hemorragia con este medicamento.")
    found = [f for f in check_packs([pack(IBUPROFENO), pack(ACENOCUMAROL)], FakeSmpc(), TODAY) if f.kind == "smpc_mention"]
    assert found and found[0].severity == "review"


def test_salt_names_are_searched_by_their_plain_name_too():
    amlodipine = med("730001", "AMLODIPINO ETA 5 mg", ["AMLODIPINO BESILATO"], "C08CA01")
    assert "amlodipino" in mention_terms(amlodipine)


def test_pdf_survives_markup_characters_and_prints_them_literally(tmp_path):
    lines = [line("Metformina 850 mg", "tomar <b si < 2 h & con agua", breakfast="1")]
    packs = [pack(METFORMINA_850, date(2030, 1, 1))]
    plan = build_plan(lines, reconcile(lines, packs), [], TODAY)
    text = pdf_text(render_pdf(plan, tmp_path / "x.pdf", "Ana <b & <font size=40>Luis"))
    flat = " ".join(text.split())
    assert "tomar <b si < 2 h & con agua" in flat and "Ana <b & <font size=40>Luis" in flat


def test_pdf_prints_both_doses_when_one_pack_has_two_entries_in_a_slot(tmp_path):
    pk = pack(METFORMINA_850, date(2030, 1, 1))
    plan = build_plan([], reconcile([], []), [], TODAY)
    plan.entries = [Entry("breakfast", pk, line("A", breakfast="1"), "1"), Entry("breakfast", pk, line("B", breakfast="2"), "2")]
    text = pdf_text(render_pdf(plan, tmp_path / "y.pdf"))
    assert "1\ntablet" in text.replace("\r", "") and "2\ntablets" in text.replace("\r", "")


def test_ics_escapes_lone_cr_and_folds_long_lines():
    lines = [line("Metformina 850 mg", "Tomar\rSUMMARY:Robada " + "ñ" * 120, breakfast="1")]
    packs = [pack(METFORMINA_850, date(2030, 1, 1))]
    ics = to_ics(build_plan(lines, reconcile(lines, packs), [], TODAY), start=date(2026, 10, 27))
    physical = ics.split("\r\n")
    assert all(len(p.encode("utf-8")) <= 75 for p in physical)
    unfolded = ics.replace("\r\n ", "")
    assert "\nSUMMARY:Robada" not in unfolded and "Tomar\\nSUMMARY:Robada" in unfolded
    assert [p for p in unfolded.split("\r\n") if p.startswith("SUMMARY:")] == ["SUMMARY:Medication: Breakfast"]
