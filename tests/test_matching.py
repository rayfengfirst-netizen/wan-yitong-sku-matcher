"""配对规则单元测试。"""

from app.matching import match_one_row, process_after_prefix, strip_dash_letter_suffixes


def test_strip_dash_letters():
    assert strip_dash_letter_suffixes("SKU- A") == "SKU"
    assert strip_dash_letter_suffixes("SKU - B") == "SKU"
    assert strip_dash_letter_suffixes("SKU - A - B") == "SKU"


def test_process_after_prefix_qty():
    s, q = process_after_prefix("XYZ- A *2")
    assert s == "XYZ"
    assert q == 2
    s, q = process_after_prefix("XYZ(3)")
    assert s == "XYZ"
    assert q == 3


def test_match_one_row_ok():
    mo = match_one_row("DEMO-SKU001- A *2", "DEMO")
    assert mo.ok
    assert mo.matched_sku == "SKU001"
    assert mo.qty == 2


def test_match_one_row_no_prefix():
    mo = match_one_row("OTHER-SKU", "DEMO")
    assert not mo.ok
    assert "不以店铺简称" in mo.reason
