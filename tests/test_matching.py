"""保守匹配规则单元测试。"""

from app.matching import (
    build_short_map,
    generate_candidates,
    normalize_real_sku,
    parse_qty,
    process_sku_table,
    safe_fraction_equivalents,
    strip_batch_suffix,
)


def test_parse_qty():
    assert parse_qty("ABC*2") == 2
    assert parse_qty("ABC(3)-E") == 3
    assert parse_qty("ABC（4）_A") == 4
    assert parse_qty("ABC") == 1


def test_strip_batch_suffix():
    assert strip_batch_suffix("SKU-A") == "SKU"
    assert strip_batch_suffix("SKU_B") == "SKU"
    assert strip_batch_suffix("LZ-ABC") == "LZ-ABC"


def test_generate_candidates_keep_both_prefix_branches():
    c = generate_candidates("LZ-ABC(2)-E", {"LZ"})
    assert "LZ-ABC(2)-E" in c
    assert "LZ-ABC" in c
    assert "ABC" in c


def test_fraction_equivalents():
    out = safe_fraction_equivalents("AUTOTOOL-SwivelHose-0.75 inch")
    assert "AUTOTOOL-SwivelHose-3/4 inch" in out


def test_real_sku_normalize_dedup():
    assert normalize_real_sku("Coil_A411001620") == normalize_real_sku("COIL-A411001620")


def test_multi_short_names_for_one_shop():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [
        {"店铺全称": "A店", "店铺简称": "AAA"},
        {"店铺全称": "A店", "店铺简称": "A1"},
    ]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)
    assert full_to_shorts["A店"] == {"AAA", "A1"}

    sku_headers = ["店铺账号", "custom Label", "万邑通SKU"]
    sku_rows = [
        {"店铺账号": "A店", "custom Label": "seed", "万邑通SKU": "SKU123"},
        {"店铺账号": "A店", "custom Label": "A1-SKU123(3)", "万邑通SKU": ""},
    ]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[1]["匹配状态"] == "成功"
    assert out[1]["匹配SKU"] == "SKU123"
    assert out[1]["数量"] == 3


def test_multi_short_names_split_in_one_cell():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "B店", "店铺简称": "BBB, B2 / B-ALT"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)
    assert full_to_shorts["B店"] == {"BBB", "B2", "B-ALT"}


def test_unique_exact_hit_only():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "LZ店", "店铺简称": "LZ"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)

    sku_headers = ["店铺账号", "custom Label", "万邑通SKU"]
    sku_rows = [
        {"店铺账号": "LZ店", "custom Label": "seed", "万邑通SKU": "LZ-ABC"},
        {"店铺账号": "LZ店", "custom Label": "LZ-ABC(2)-E", "万邑通SKU": ""},
    ]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[1]["匹配状态"] == "成功"
    assert out[1]["匹配SKU"] == "LZ-ABC"
    assert out[1]["数量"] == 2


def test_ambiguous_should_fail():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "店铺A", "店铺简称": "AA"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)

    sku_headers = ["店铺账号", "custom Label", "万邑通SKU"]
    sku_rows = [
        {"店铺账号": "店铺A", "custom Label": "seed", "万邑通SKU": "ABC"},
        {"店铺账号": "店铺A", "custom Label": "seed", "万邑通SKU": "ABC-E"},
        {"店铺账号": "店铺A", "custom Label": "AA-ABC-E", "万邑通SKU": ""},
    ]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[2]["匹配状态"] == "失败"
    assert "歧义" in out[2]["失败原因"] or "多个真实SKU" in out[2]["失败原因"]


def test_match_by_removing_embedded_parenthesized_qty():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "11 - LiiQuiiPart", "店铺简称": "Li"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)

    sku_headers = ["店铺账号", "custom Label", "万邑通SKU"]
    sku_rows = [
        {"店铺账号": "11 - LiiQuiiPart", "custom Label": "seed", "万邑通SKU": "Clamp-10294"},
        {"店铺账号": "11 - LiiQuiiPart", "custom Label": "Li-Clamp-10294(2)-E", "万邑通SKU": ""},
    ]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[1]["匹配状态"] == "成功"
    assert out[1]["匹配SKU"] == "Clamp-10294"


def test_high_risk_home_hit_blocked():
    map_headers = ["店铺全称", "店铺简称"]
    map_rows = [{"店铺全称": "12-yeeranterpart", "店铺简称": "ye"}]
    full_to_shorts, _ = build_short_map(map_rows, map_headers)
    sku_headers = ["店铺账号", "custom Label", "万邑通SKU"]
    sku_rows = [
        {"店铺账号": "12-yeeranterpart", "custom Label": "seed", "万邑通SKU": "Home-Light-W11042554"},
        {"店铺账号": "12-yeeranterpart", "custom Label": "ye-Home-Light-W11042554-C", "万邑通SKU": ""},
    ]
    out = process_sku_table(sku_headers, sku_rows, full_to_shorts)
    assert out[1]["匹配状态"] == "失败"
    assert "高风险" in out[1]["失败原因"]
