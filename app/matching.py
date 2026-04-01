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
    """去掉末尾形如「 - A」「 - ABCD」的片段（可多次）。"""
    s = raw.rstrip()
    # 仅去掉像 "- A" / "- ABCD" 这类“短字母标签”后缀；
    # 要求短码前有分隔空格，避免误删真实 SKU 段（如 LZ-ABC）。
    pat = re.compile(r"\s*-\s+[A-Za-z]{1,4}\s*$")
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


def strip_terminal_dash_single_letter(raw: str) -> str:
    """去掉末尾单字母段，如 SKU-...-G -> SKU-...。"""
    return re.sub(r"\s*-\s*([A-Za-z])\s*$", "", raw).strip()


def strip_embedded_qty_tokens(raw: str) -> str:
    """去掉任意位置的数量标记，如 (2)、( 3 )、*2、* 4。"""
    s = re.sub(r"\(\s*\d+\s*\)", "", raw)
    s = re.sub(r"\*\s*\d+", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


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
    col_real = resolve_column(sku_headers, SKU_REAL_ALIASES)
    if not col_acc:
        raise ValueError("SKU 表缺少「店铺账号」列（或与全称对应的列）")
    if not col_label:
        raise ValueError("SKU 表缺少「Custom Label」列")

    def normalize_key(v: str) -> str:
        return str(v).strip().lower()

    # 构建真实 SKU 候选库：按店铺账号分组 + 全局（用于兜底）
    real_pool_by_account: dict[str, set[str]] = {}
    real_pool_global: set[str] = set()
    if col_real:
        for row in sku_rows:
            real_val = row.get(col_real)
            real_sku = str(real_val).strip() if real_val is not None else ""
            if not real_sku:
                continue
            acc_v = row.get(col_acc)
            acc_s = str(acc_v).strip() if acc_v is not None else ""
            if acc_s:
                real_pool_by_account.setdefault(acc_s, set()).add(real_sku)
            real_pool_global.add(real_sku)

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

        label_str = str(label).strip() if label is not None else ""
        if not label_str:
            base["匹配SKU"] = ""
            base["数量"] = ""
            base["匹配状态"] = "失败"
            base["失败原因"] = "Custom Label 为空"
            out.append(base)
            continue

        # 数量优先从末尾提取：*2 / (2) 等
        after_qty, qty = extract_trailing_qty(label_str)

        # 候选1：原样去数量 + 去末尾 -ABCD
        base_candidate = strip_dash_letter_suffixes(after_qty).strip()
        candidates: list[str] = []
        seen_candidates: set[str] = set()

        def add_candidate(v: str) -> None:
            vv = v.strip()
            if not vv:
                return
            k = normalize_key(vv)
            if k in seen_candidates:
                return
            seen_candidates.add(k)
            candidates.append(vv)

        add_candidate(base_candidate)
        add_candidate(strip_terminal_dash_single_letter(base_candidate))
        add_candidate(strip_embedded_qty_tokens(base_candidate))
        add_candidate(strip_terminal_dash_single_letter(strip_embedded_qty_tokens(base_candidate)))

        # 候选2：尝试去掉店铺简称前缀（但保留原样候选，避免 LZ- 与真实 SKU 冲突）
        for short in sorted(short_list, key=len, reverse=True):
            short_clean = short.strip()
            if not short_clean:
                continue
            if base_candidate.startswith(short_clean):
                rest = base_candidate[len(short_clean) :].lstrip("-_ ")
                add_candidate(rest)
                add_candidate(strip_terminal_dash_single_letter(rest))
                add_candidate(strip_embedded_qty_tokens(rest))
                add_candidate(strip_terminal_dash_single_letter(strip_embedded_qty_tokens(rest)))

        # 在真实 SKU 候选库中做精确匹配（先店铺内，再全局兜底）
        account_pool = real_pool_by_account.get(acc_str, set())
        account_pool_idx = {normalize_key(x): x for x in account_pool}
        global_pool_idx = {normalize_key(x): x for x in real_pool_global}

        matched_real = ""
        for cand in candidates:
            ck = normalize_key(cand)
            if ck in account_pool_idx:
                matched_real = account_pool_idx[ck]
                break
        if not matched_real:
            for cand in candidates:
                ck = normalize_key(cand)
                if ck in global_pool_idx:
                    matched_real = global_pool_idx[ck]
                    break

        if matched_real:
            base["匹配SKU"] = matched_real
            base["数量"] = qty
            base["匹配状态"] = "成功"
            base["失败原因"] = ""
            out.append(base)
            continue

        # 若没有真实 SKU 候选库，则退回旧逻辑（直接按前后缀算）
        if not real_pool_global:
            mo = MatchOutcome(False, "", 1, "Custom Label 不匹配该店铺任一简称")
            for short in sorted(short_list, key=len, reverse=True):
                mo = match_one_row(label_str, short)
                if mo.ok:
                    break
            base["匹配SKU"] = mo.matched_sku if mo.ok else ""
            base["数量"] = mo.qty if mo.ok else ""
            base["匹配状态"] = "成功" if mo.ok else "失败"
            base["失败原因"] = mo.reason if not mo.ok else ""
            out.append(base)
            continue

        base["匹配SKU"] = ""
        base["数量"] = ""
        base["匹配状态"] = "失败"
        base["失败原因"] = (
            "未在万邑通SKU候选库中匹配到真实SKU；"
            f"候选值={candidates}"
        )
        out.append(base)
    return out
