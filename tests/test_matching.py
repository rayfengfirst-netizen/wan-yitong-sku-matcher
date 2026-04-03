"""万邑通SKU池 + 精确/近似匹配 单元测试。"""

from app.matching import (
    build_short_map,
    collect_row_candidates,
    process_sku_table,
)


def _map_ye():
    m, _ = build_short_map(
        [{"店铺全称": "12-yeeranterpart", "店铺简称": "ye"}],
        ["店铺全称", "店铺简称"],
    )
    return m


def test_pool_aggregate_not_per_row():
    full_to_shorts = _map_ye()
    headers = ["店铺账号", "custom Label", "万邑通SKU"]
    rows = [
        {"店铺账号": "12-yeeranterpart", "custom Label": "ignore", "万邑通SKU": "Home-WasherArm-5304518927"},
        {
            "店铺账号": "12-yeeranterpart",
            "custom Label": "ye-Home-WasherArm-5304518927-G",
            "万邑通SKU": "",
        },
    ]
    out = process_sku_table(headers, rows, full_to_shorts)
    assert out[1]["匹配状态"] == "成功"
    assert out[1]["匹配SKU"] == "Home-WasherArm-5304518927"
    assert out[1]["近似匹配"] == ""


def test_type2_no_prefix():
    full_to_shorts = _map_ye()
    headers = ["店铺账号", "custom Label", "万邑通SKU"]
    rows = [
        {"店铺账号": "12-yeeranterpart", "custom Label": "x", "万邑通SKU": "Clamp-10294"},
        {"店铺账号": "12-yeeranterpart", "custom Label": "Clamp-10294(2)-E", "万邑通SKU": ""},
    ]
    out = process_sku_table(headers, rows, full_to_shorts)
    assert out[1]["匹配SKU"] == "Clamp-10294"


def test_lz_branch():
    full_to_shorts, _ = build_short_map(
        [{"店铺全称": "LZ店", "店铺简称": "LZ"}],
        ["店铺全称", "店铺简称"],
    )
    headers = ["店铺账号", "custom Label", "万邑通SKU"]
    rows = [
        {"店铺账号": "LZ店", "custom Label": "x", "万邑通SKU": "LZ-HOSE596-2"},
        {"店铺账号": "LZ店", "custom Label": "LZ-LZ-HOSE596-2", "万邑通SKU": ""},
    ]
    out = process_sku_table(headers, rows, full_to_shorts)
    assert out[1]["匹配SKU"] == "LZ-HOSE596-2"


def test_fuzzy_fills_approx_column():
    full_to_shorts = _map_ye()
    headers = ["店铺账号", "custom Label", "万邑通SKU"]
    rows = [
        {"店铺账号": "12-yeeranterpart", "custom Label": "x", "万邑通SKU": "EXACT-SKU-12345"},
        {"店铺账号": "12-yeeranterpart", "custom Label": "ye-EXACT-SKU-12345X-G", "万邑通SKU": ""},
    ]
    out = process_sku_table(headers, rows, full_to_shorts)
    assert out[1]["匹配SKU"] == ""
    assert out[1]["近似匹配"] == "EXACT-SKU-12345"
    assert out[1]["匹配状态"] == "成功"


def test_fuzzy_writes_bilingual_approx_header():
    """双语表头时，近似匹配必须写在实际表头键上，否则导出 xlsx 该列为空。"""
    full_to_shorts = _map_ye()
    h_approx = "近似匹配\nFuzzy"
    headers = ["店铺账号", "custom Label", "万邑通SKU", "匹配SKU", h_approx, "数量"]
    rows = [
        {
            "店铺账号": "12-yeeranterpart",
            "custom Label": "x",
            "万邑通SKU": "EXACT-SKU-12345",
            "匹配SKU": "",
            h_approx: "",
            "数量": "",
        },
        {
            "店铺账号": "12-yeeranterpart",
            "custom Label": "ye-EXACT-SKU-12345X-G",
            "万邑通SKU": "",
            "匹配SKU": "",
            h_approx: "",
            "数量": "",
        },
    ]
    out = process_sku_table(headers, rows, full_to_shorts)
    assert out[1][h_approx] == "EXACT-SKU-12345"
    assert out[1]["匹配SKU"] == ""


def test_empty_pool_raises():
    import pytest

    full_to_shorts = _map_ye()
    headers = ["店铺账号", "custom Label", "万邑通SKU"]
    rows = [{"店铺账号": "12-yeeranterpart", "custom Label": "a", "万邑通SKU": ""}]
    with pytest.raises(ValueError, match="万邑通SKU"):
        process_sku_table(headers, rows, full_to_shorts)


def test_collect_candidates_has_prefix_and_lz():
    shorts = {"ye", "LZ"}
    c = collect_row_candidates("ye-LZ-ABC-G", shorts)
    assert any("ABC" in x or x.endswith("ABC") for x in c)
