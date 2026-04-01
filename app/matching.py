"""SKU逆向还原：标准化 + 候选生成 + 唯一精确命中。"""

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
SKU_REAL_ALIASES = ["万邑通SKU", "万邑通 sku", "winit sku", "真实SKU", "真实sku"]


@dataclass
class MatchOutcome:
    ok: bool
    matched_sku: str
    qty: int
    reason: str


def build_short_map(
    mapping_rows: list[dict[str, Any]],
    map_headers: list[str],
) -> tuple[dict[str, set[str]], list[str]]:
    """店铺全称 -> 店铺简称列表（支持一店多简称）。"""
    col_full = resolve_column(map_headers, MAP_FULL_ALIASES)
    col_short = resolve_column(map_headers, MAP_SHORT_ALIASES)
    if not col_full or not col_short:
        raise ValueError(
            "配对关系表缺少必需列：需要「店铺全称」（或店铺账号）与「店铺简称」"
        )
    m: dict[str, set[str]] = {}
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
            m[fk] = set()
        before = len(m[fk])
        for sk in names:
            m[fk].add(sk)
        if len(m[fk]) > before:
            warnings.append(
                f"配对表第{i}行：店铺「{fk}」新增简称 {names}，当前共 {len(m[fk])} 个简称"
            )
    if not m:
        raise ValueError("配对关系表没有有效数据行")
    logger.info("配对表加载: %s 条 店铺映射（含一店多简称）", len(m))
    return m, warnings


def strip_batch_suffix(raw: str) -> str:
    """去掉刊登批次后缀：-A/-B/_A（仅末尾1位字母）。"""
    s = raw.rstrip()
    return re.sub(r"[-_]\s*[A-Za-z]\s*$", "", s).strip()


def parse_qty(label: str) -> int:
    """提取数量，默认1。仅当能明确提取到单一数字时生效。"""
    tokens = re.findall(r"\*\s*(\d+)|[\(（]\s*(\d+)\s*[\)）]", label)
    nums = []
    for a, b in tokens:
        n = a or b
        if n:
            nums.append(int(n))
    if not nums:
        return 1
    uniq = sorted(set(nums))
    if len(uniq) == 1:
        return uniq[0]
    # 出现多个不同数字，不做激进猜测
    return 1


def strip_qty_tokens(raw: str) -> str:
    """去掉任意位置数量标记：*2/(2)/（2）。"""
    s = re.sub(r"\*\s*\d+", "", raw)
    s = re.sub(r"[\(（]\s*\d+\s*[\)）]", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def normalize_key(v: str) -> str:
    return str(v).strip().lower()


def generate_candidates(label: str, shop_prefixes: set[str]) -> list[str]:
    """保守候选生成：原样分支 + 去数量 + 去批次后缀 + 去店铺前缀分支。"""
    cand: list[str] = []
    seen: set[str] = set()

    def add(v: str) -> None:
        vv = str(v).strip()
        if not vv:
            return
        k = normalize_key(vv)
        if k in seen:
            return
        seen.add(k)
        cand.append(vv)

    base = label.strip()
    add(base)
    no_qty = strip_qty_tokens(base)
    add(no_qty)
    no_batch = strip_batch_suffix(no_qty)
    add(no_batch)

    for p in sorted((x.strip() for x in shop_prefixes if x and str(x).strip()), key=len, reverse=True):
        if base.startswith(p):
            rest = base[len(p) :].lstrip("-_ ")
            add(rest)
            add(strip_qty_tokens(rest))
            add(strip_batch_suffix(strip_qty_tokens(rest)))
    return cand


def process_sku_table(
    sku_headers: list[str],
    sku_rows: list[dict[str, Any]],
    full_to_shorts: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """返回输出行：只在唯一高置信精确命中时写入匹配SKU。"""
    col_acc = resolve_column(sku_headers, SKU_ACCOUNT_ALIASES)
    col_label = resolve_column(sku_headers, SKU_LABEL_ALIASES)
    col_real = resolve_column(sku_headers, SKU_REAL_ALIASES)
    if not col_acc:
        raise ValueError("SKU 表缺少「店铺账号」列（或与全称对应的列）")
    if not col_label:
        raise ValueError("SKU 表缺少「Custom Label」列")

    # 构建真实 SKU 候选库（同店铺 + 全局）；索引值保留原文，key用lower精确匹配
    real_pool_by_account: dict[str, dict[str, set[str]]] = {}
    real_pool_global: dict[str, set[str]] = {}
    if col_real:
        for row in sku_rows:
            real_val = row.get(col_real)
            real_sku = str(real_val).strip() if real_val is not None else ""
            if not real_sku:
                continue
            rk = normalize_key(real_sku)
            acc_v = row.get(col_acc)
            acc_s = str(acc_v).strip() if acc_v is not None else ""
            if acc_s:
                real_pool_by_account.setdefault(acc_s, {}).setdefault(rk, set()).add(real_sku)
            real_pool_global.setdefault(rk, set()).add(real_sku)

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
            base["匹配审计"] = "NO_ACCOUNT"
            out.append(base)
            continue
        short_list = full_to_shorts.get(acc_str)
        if not short_list:
            base["匹配SKU"] = ""
            base["数量"] = ""
            base["匹配状态"] = "失败"
            base["失败原因"] = f"配对表中找不到店铺全称/账号「{acc_str}」"
            base["匹配审计"] = "NO_SHOP_PREFIX"
            out.append(base)
            continue

        label_str = str(label).strip() if label is not None else ""
        if not label_str:
            base["匹配SKU"] = ""
            base["数量"] = ""
            base["匹配状态"] = "失败"
            base["失败原因"] = "Custom Label 为空"
            base["匹配审计"] = "EMPTY_LABEL"
            out.append(base)
            continue

        qty = parse_qty(label_str)
        candidates = generate_candidates(label_str, short_list)
        pool_acc = real_pool_by_account.get(acc_str, {})

        # 只接受“唯一精确命中”
        hit_values: set[str] = set()
        hit_from_acc = False
        for c in candidates:
            ck = normalize_key(c)
            vals = pool_acc.get(ck)
            if vals:
                hit_values.update(vals)
                hit_from_acc = True
            else:
                gvals = real_pool_global.get(ck)
                if gvals:
                    hit_values.update(gvals)

        if len(hit_values) == 1:
            base["匹配SKU"] = next(iter(hit_values))
            base["数量"] = qty
            base["匹配状态"] = "成功"
            base["失败原因"] = ""
            base["匹配审计"] = (
                f"UNIQUE_EXACT;scope={'ACCOUNT' if hit_from_acc else 'GLOBAL'};"
                f"candidates={candidates[:8]}"
            )
            out.append(base)
            continue

        base["匹配SKU"] = ""
        base["数量"] = ""
        base["匹配状态"] = "失败"
        if len(hit_values) > 1:
            base["失败原因"] = f"命中多个真实SKU，存在歧义：{sorted(hit_values)[:6]}"
            base["匹配审计"] = f"AMBIGUOUS;hits={len(hit_values)};candidates={candidates[:8]}"
        else:
            base["失败原因"] = f"未在万邑通SKU候选库中匹配到真实SKU；候选值={candidates}"
            base["匹配审计"] = f"NO_HIT;candidates={candidates[:8]}"
        out.append(base)
    return out
