"""Codigo Nacional check digit and GS1 parsing."""

from datetime import date


from helpers import ntin_element_string
from medtable import cn, gs1

# CNs read from real CIMA pack photos whose 7th digit was also present in CIMA's list of presentations (6 digits)
REAL_CNS = [("725702", 8), ("698809", 1), ("682811", 3), ("672339", 5), ("848226", 9)]


def test_check_digit_matches_real_codes():
    for cn6, digit in REAL_CNS:
        assert cn.check_digit(cn6) == digit and cn.is_valid(f"{cn6}{digit}") and cn.is_valid(f"{cn6}.{digit}")


def test_wrong_digit_and_garbage_are_rejected():
    assert not cn.is_valid("7257020")
    assert not cn.is_valid("72570")
    assert cn.find_cn("C.N. 725702.8 O") == "7257028"
    assert cn.find_cn("lote 123") is None


def test_parse_human_readable_ntin():
    code = gs1.parse_pack_code(ntin_element_string("848226"))
    assert code.gtin == "08470008482269"
    assert code.expiry == date(2028, 12, 31)
    assert (code.lot, code.serial) == ("LOT123", "SN0001")
    assert code.national.cn == "8482269" and code.national.source == "ntin"


def test_parse_raw_string_with_group_separator():
    raw = "010847000848226917281231" + "10LOT123" + gs1.GS + "21SN0001"
    fields = gs1.parse_elements("]d2" + raw)
    assert fields == {"01": "08470008482269", "17": "281231", "10": "LOT123", "21": "SN0001"}
    assert gs1.parse_elements(raw.replace(gs1.GS, "<GS>")) == fields


def test_expiry_day_zero_is_end_of_month():
    assert gs1.parse_expiry("280200") == date(2028, 2, 29)
    assert gs1.parse_expiry("270200") == date(2027, 2, 28)


def test_bad_check_digit_never_yields_a_cn():
    fields = gs1.parse_elements("(01)08470008482260(17)281231")  # last digit should be 9
    result = gs1.national_code(fields)
    assert result.cn is None
    assert result.problems
