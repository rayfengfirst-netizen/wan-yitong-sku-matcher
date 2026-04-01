"""配对规则单元测试。"""

from app.matching import (
    build_short_map,
    match_one_row,
    process_after_prefix,
    process_sku_table,
    strip_dash_letter_suffixes,
)


def test_strip_dash_letters():
    assert strip_dash_letter_suffixes("SKU- A") == "SKU"
    assert strip_dash_letter_suffixes("SKU - B") == "SKU"
    assert strip_dash_letter_suffixes("SKU - A - B") == "SKU"
    assert strip_dash_letter_suffixes("SKU - ABCD") == "SKU"


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


def test_multi_short_names_for_one_shop():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [
        {"店铺全称": "A店", "店铺简称": "AAA"},
        {"店铺全称": "A店", "店铺简称": "A1"},
    ]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)
    assert full_to_shorts["A店"] == ["AAA", "A1"]

    sku_headers = ["店铺账号", "custom Label"]
    sku_rows = [{"店铺账号": "A店", "custom Label": "A1-SKU123(3)"}]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[0]["匹配状态"] == "成功"
    assert out[0]["匹配SKU"] == "SKU123"
    assert out[0]["数量"] == 3


def test_multi_short_names_split_in_one_cell():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "B店", "店铺简称": "BBB, B2 / B-ALT"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)
    assert full_to_shorts["B店"] == ["BBB", "B2", "B-ALT"]


def test_real_winit_sku_pool_match_with_prefix_conflict():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "LZ店", "店铺简称": "LZ"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)

    sku_headers = ["店铺账号", "custom Label", "万邑通SKU"]
    sku_rows = [
        # 前两行提供该店铺真实 SKU 候选库
        {"店铺账号": "LZ店", "custom Label": "x", "万邑通SKU": "LZ-ABC"},
        {"店铺账号": "LZ店", "custom Label": "x", "万邑通SKU": "REAL-001"},
        # 目标行：带 LZ- 前缀，不应错误去前缀成 ABC
        {"店铺账号": "LZ店", "custom Label": "LZ-ABC- A *2", "万邑通SKU": ""},
        # 目标行：无前缀，也要能命中真实 SKU
        {"店铺账号": "LZ店", "custom Label": "REAL-001(3)", "万邑通SKU": ""},
    ]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[2]["匹配状态"] == "成功"
    assert out[2]["匹配SKU"] == "LZ-ABC"
    assert out[2]["数量"] == 2
    assert out[3]["匹配状态"] == "成功"
    assert out[3]["匹配SKU"] == "REAL-001"
    assert out[3]["数量"] == 3
