"""SKU 配对：去简称前缀 + 后缀清理 + 数量提取。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.table_io import resolve_column

logger = logging.getLogger(__name__)

# 店铺简称配对关系表
MAP_FULL_ALIASES = ["店铺全称", "店铺账号", "全称", "账号全称"]
MAP_SHORT_ALIASES = ["店铺简称", "简称"]

# SKU 表
SKU_ACCOUNT_ALIASES = ["店铺账号", "店铺全称", "账号", "selleraccount"]
SKU_LABEL_ALIASES = [
    "Custom Label",
    "custom Label",
    "custom label",
    "CustomLabel",
    "自定义标签",
    "customlabel",
]


@dataclass
class MatchOutcome:
    ok: bool
    matched_sku: str
    qty: int
    reason: str


def build_short_map(
    mapping_rows: list[dict[str, Any]],
    map_headers: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """店铺全称 -> 店铺简称列表（支持一店多简称）。"""
    col_full = resolve_column(map_headers, MAP_FULL_ALIASES)
    col_short = resolve_column(map_headers, MAP_SHORT_ALIASES)
    if not col_full or not col_short:
        raise ValueError(
            "配对关系表缺少必需列：需要「店铺全称」（或店铺账号）与「店铺简称」"
        )
    m: dict[str, list[str]] = {}
    warnings: list[str] = []

    def split_short_names(raw: str) -> list[str]:
        parts = re.split(r"[,\|/，、；;]+", raw)
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            v = str(p).strip()
            if not v or v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out

    for i, row in enumerate(mapping_rows, start=2):
        full = row.get(col_full)
        short = row.get(col_short)
        if full is None or str(full).strip() == "":
            continue
        if short is None or str(short).strip() == "":
            continue
        fk = str(full).strip()
        names = split_short_names(str(short))
        if not names:
            continue
        if fk not in m:
            m[fk] = []
        before = len(m[fk])
        for sk in names:
            if sk not in m[fk]:
                m[fk].append(sk)
        if len(m[fk]) > before:
            warnings.append(
                f"配对表第{i}行：店铺「{fk}」新增简称 {names}，当前共 {len(m[fk])} 个简称"
            )
    if not m:
        raise ValueError("配对关系表没有有效数据行")
    logger.info("配对表加载: %s 条 店铺映射（含一店多简称）", len(m))
    return m, warnings


def strip_dash_letter_suffixes(raw: str) -> str:
    """去掉末尾形如「 - A」「 - B」的片段（可多次）。"""
    s = raw.rstrip()
    pat = re.compile(r"\s*-\s*[A-Za-z]\s*$")
    while True:
        ns = pat.sub("", s).rstrip()
        if ns == s:
            return s
        s = ns


def extract_trailing_qty(s: str) -> tuple[str, int]:
    """
    去掉末尾 *数字 或 (数字)，并返回数量；无则数量为 1。
    只处理串在**最右端**的一段。
    """
    s = s.rstrip()
    qty = 1
    # (2) (3)
    m = re.search(r"\(\s*(\d+)\s*\)\s*$", s)
    if m:
        qty = int(m.group(1))
        s = s[: m.start()].rstrip()
        return s, qty
    # *2 *3（允许前面无空格）
    m = re.search(r"\*\s*(\d+)\s*$", s)
    if m:
        qty = int(m.group(1))
        s = s[: m.start()].rstrip()
        return s, qty
    return s, 1


def process_after_prefix(remainder: str) -> tuple[str, int]:
    """先做 2.1 去字母后缀，再做 2.2 数量后缀（文档顺序）。"""
    s = strip_dash_letter_suffixes(remainder)
    s, qty = extract_trailing_qty(s)
    s = strip_dash_letter_suffixes(s)
    s = s.strip()
    return s, qty


def match_one_row(
    custom_label: str,
    short_name: str,
) -> MatchOutcome:
    label = str(custom_label).strip()
    short = str(short_name).strip()
    if not label:
        return MatchOutcome(False, "", 1, "Custom Label 为空")
    if not short:
        return MatchOutcome(False, "", 1, "店铺简称为空")
    if not label.startswith(short):
        return MatchOutcome(
            False,
            "",
            1,
            f"Custom Label 不以店铺简称「{short}」开头，无法去前缀",
        )
    rest = label[len(short) :]
    rest = rest.lstrip("-_ ")
    if not rest:
        return MatchOutcome(False, "", 1, "去掉店铺简称后没有剩余 SKU 内容")
    matched, qty = process_after_prefix(rest)
    if not matched:
        return MatchOutcome(False, "", qty, "后缀处理后 SKU 为空")
    return MatchOutcome(True, matched, qty, "")


def process_sku_table(
    sku_headers: list[str],
    sku_rows: list[dict[str, Any]],
    full_to_shorts: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """返回输出行：原列 + 匹配SKU + 数量 + 匹配状态 + 失败原因。"""
    col_acc = resolve_column(sku_headers, SKU_ACCOUNT_ALIASES)
    col_label = resolve_column(sku_headers, SKU_LABEL_ALIASES)
    if not col_acc:
        raise ValueError("SKU 表缺少「店铺账号」列（或与全称对应的列）")
    if not col_label:
        raise ValueError("SKU 表缺少「Custom Label」列")

    out: list[dict[str, Any]] = []
    for idx, row in enumerate(sku_rows, start=2):
        account = row.get(col_acc)
        label = row.get(col_label)
        base: dict[str, Any] = {k: row.get(k, "") for k in sku_headers}
        acc_str = str(account).strip() if account is not None else ""
        if not acc_str:
            base["匹配SKU"] = ""
            base["数量"] = ""
            base["匹配状态"] = "失败"
            base["失败原因"] = "店铺账号为空"
            out.append(base)
            continue
        short_list = full_to_shorts.get(acc_str)
        if not short_list:
            base["匹配SKU"] = ""
            base["数量"] = ""
            base["匹配状态"] = "失败"
            base["失败原因"] = f"配对表中找不到店铺全称/账号「{acc_str}」"
            out.append(base)
            continue
        mo = MatchOutcome(False, "", 1, "Custom Label 不匹配该店铺任一简称")
        for short in sorted(short_list, key=len, reverse=True):
            mo = match_one_row(label, short)
            if mo.ok:
                break
        if not mo.ok:
            mo = MatchOutcome(
                False,
                "",
                1,
                f"Custom Label 不以该店铺任何简称开头：{', '.join(short_list)}",
            )
        base["匹配SKU"] = mo.matched_sku if mo.ok else ""
        base["数量"] = mo.qty if mo.ok else ""
        base["匹配状态"] = "成功" if mo.ok else "失败"
        base["失败原因"] = mo.reason if not mo.ok else ""
        out.append(base)
    return out
