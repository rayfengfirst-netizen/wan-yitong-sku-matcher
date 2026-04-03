"""SKU 匹配：按业务算法将 custom Label 还原为万邑通SKU（全表 SKU 池 + 精确 + 近似）。"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from app.table_io import resolve_column

logger = logging.getLogger(__name__)

MAP_FULL_ALIASES = ["店铺全称", "店铺账号", "全称", "账号全称"]
MAP_SHORT_ALIASES = ["店铺简称", "简称"]

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

# 结果列：写入时必须用表头「实际字符串」，否则 xlsx 导出按原表头取格会读到空
SKU_OUT_MATCH_ALIASES = ["匹配SKU", "匹配 sku", "matchedsku"]
SKU_OUT_APPROX_ALIASES = ["近似匹配", "近似 sku", "fuzzymatch"]
SKU_OUT_QTY_ALIASES = ["数量", "qty", "quantity"]
SKU_OUT_STATUS_ALIASES = ["匹配状态", "matchstatus"]
SKU_OUT_FAIL_ALIASES = ["失败原因", "failreason"]
SKU_OUT_AUDIT_ALIASES = ["匹配审计", "matchaudit"]


def _resolve_output_column(headers: list[str], aliases: list[str], fallback: str) -> str:
    return resolve_column(headers, aliases) or fallback


# 近似匹配：宁可少匹配也不要乱匹配
FUZZY_MIN_RATIO = 0.88
FUZZY_MIN_MARGIN = 0.04


def build_short_map(
    mapping_rows: list[dict[str, Any]],
    map_headers: list[str],
) -> tuple[dict[str, set[str]], list[str]]:
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


def normalize_separators(s: str) -> str:
    s = str(s)
    s = s.replace("—", "-").replace("–", "-").replace("_", "-")
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def normalize_shop_prefix_token(prefix: str) -> str:
    return normalize_separators(prefix).strip().rstrip("-")


def normalize_real_sku(v: str) -> str:
    return normalize_separators(v).lower()


def clean_label_prefix_noise(label: str, shop_prefixes: set[str]) -> str:
    s = normalize_separators(label)
    prefixes = sorted(
        {normalize_shop_prefix_token(x) for x in shop_prefixes if str(x).strip()},
        key=len,
        reverse=True,
    )
    for p in prefixes:
        if not p:
            continue
        s = re.sub(rf"^a{re.escape(p)}-", f"{p}-", s, flags=re.I)
        spaced = "-".join(list(p))
        s = re.sub(rf"^{re.escape(spaced)}-", f"{p}-", s, flags=re.I)
        s = re.sub(rf"^(?:{re.escape(p)}){{2,}}-", f"{p}-", s, flags=re.I)
    return s


def strip_batch_suffix(raw: str) -> str:
    s = raw.rstrip()
    return re.sub(r"[-_]\s*[A-Za-z]\s*$", "", s).strip()


def strip_all_batch_suffixes(s: str) -> str:
    t = s
    while True:
        u = strip_batch_suffix(t)
        if u == t:
            return t
        t = u


def parse_qty(label: str) -> int:
    tokens = re.findall(r"\*\s*(\d+)|[\(（]\s*(\d+)\s*[\)）]", label)
    nums: list[int] = []
    for a, b in tokens:
        n = a or b
        if n:
            nums.append(int(n))
    if not nums:
        return 1
    uniq = sorted(set(nums))
    if len(uniq) == 1:
        return uniq[0]
    return 1


def strip_qty_tokens(raw: str) -> str:
    s = re.sub(r"\*\s*\d+", "", raw)
    s = re.sub(r"[\(（]\s*\d+\s*[\)）]", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def safe_fraction_equivalents(s: str) -> list[str]:
    pairs = [
        (r"0\.75\s*inch", "3/4 inch"),
        (r"3/4\s*inch", "0.75 inch"),
        (r"0\.5\s*inch", "1/2 inch"),
        (r"1/2\s*inch", "0.5 inch"),
        (r"0\.25\s*inch", "1/4 inch"),
        (r"1/4\s*inch", "0.25 inch"),
    ]
    out: list[str] = []
    for pat, repl in pairs:
        if re.search(pat, s, flags=re.I):
            out.append(normalize_separators(re.sub(pat, repl, s, flags=re.I)))
    return out


def _build_winit_pool_impl(
    sku_rows: list[dict[str, Any]],
    col_real: str,
) -> tuple[dict[str, str], list[str]]:
    norm_to_canon: dict[str, str] = {}
    order: list[str] = []
    for row in sku_rows:
        rv = row.get(col_real)
        s = str(rv).strip() if rv is not None else ""
        if not s:
            continue
        nk = normalize_real_sku(s)
        if nk not in norm_to_canon:
            norm_to_canon[nk] = s
            order.append(s)
    return norm_to_canon, order


def try_strip_shop_prefix(s: str, prefix: str) -> str | None:
    """若 s 以该店铺简称开头（后跟 -/_ 或整段即简称），返回去掉前缀后的主体。"""
    p = normalize_shop_prefix_token(prefix)
    if not p:
        return None
    m = re.match(re.escape(p) + r"(?:[-_]|$)", s, flags=re.I)
    if not m:
        return None
    end = m.end()
    if end >= len(s):
        return ""
    rest = s[end:].lstrip("-_ ")
    return normalize_separators(rest) if rest else ""


def collect_row_candidates(label_raw: str, shop_prefixes: set[str]) -> list[str]:
    """
    类型1：含店铺前缀 → 去前缀 + 去批次 + 去数量
    类型2：不含店铺前缀 → 仅去批次 + 去数量
    类型3：LZ- 与真实 SKU 均可能含 LZ- → 保留原样 + 尝试去掉首段 LZ-
    全部并入候选（去重），再对万邑通SKU池做精确/近似。
    """
    seen: set[str] = set()
    out: list[str] = []

    def add(x: str) -> None:
        v = normalize_separators(x.strip())
        if not v:
            return
        k = normalize_real_sku(v)
        if k in seen:
            return
        seen.add(k)
        out.append(v)

    base = clean_label_prefix_noise(label_raw.strip(), shop_prefixes)
    base = normalize_separators(base)
    s = strip_all_batch_suffixes(strip_qty_tokens(base))
    add(s)
    for alt in safe_fraction_equivalents(s):
        add(alt)

    # 类型1：按最长简称优先尝试去前缀
    stripped_any = False
    for pref in sorted(
        {str(x).strip() for x in shop_prefixes if str(x).strip()},
        key=len,
        reverse=True,
    ):
        rest = try_strip_shop_prefix(s, pref)
        if rest is not None and rest != s:
            stripped_any = True
            add(rest)
            add(strip_all_batch_suffixes(strip_qty_tokens(rest)))

    # 类型3：LZ- 双分支（无论是否已去店铺前缀）
    if re.match(r"^LZ[-_]", s, flags=re.I):
        m = re.match(r"^LZ[-_]", s, flags=re.I)
        if m:
            tail = s[m.end() :].lstrip("-_ ")
            if tail:
                add(normalize_separators(tail))
                add(strip_all_batch_suffixes(strip_qty_tokens(tail)))

    # 若完全没去前缀且上面没产生额外候选，s 已包含「无前缀」情形（类型2）
    if not stripped_any:
        pass

    return out


def fuzzy_best_canonical(query_norm: str, norm_to_canon: dict[str, str]) -> str | None:
    if not query_norm or not norm_to_canon:
        return None
    best_r = -1.0
    second_r = -1.0
    best_canon: str | None = None
    for nk, canon in norm_to_canon.items():
        r = SequenceMatcher(None, query_norm, nk).ratio()
        if r > best_r:
            second_r = best_r
            best_r = r
            best_canon = canon
        elif r > second_r:
            second_r = r
    if best_canon is None:
        return None
    if best_r < FUZZY_MIN_RATIO:
        return None
    if best_r - second_r < FUZZY_MIN_MARGIN and second_r >= FUZZY_MIN_RATIO - 0.05:
        return None
    return best_canon


def process_sku_table(
    sku_headers: list[str],
    sku_rows: list[dict[str, Any]],
    full_to_shorts: dict[str, set[str]],
) -> list[dict[str, Any]]:
    col_acc = resolve_column(sku_headers, SKU_ACCOUNT_ALIASES)
    col_label = resolve_column(sku_headers, SKU_LABEL_ALIASES)
    col_real = resolve_column(sku_headers, SKU_REAL_ALIASES)
    if not col_acc:
        raise ValueError("SKU 表缺少「店铺账号」列（或与全称对应的列）")
    if not col_label:
        raise ValueError("SKU 表缺少「Custom Label」列")
    if not col_real:
        raise ValueError("SKU 表缺少「万邑通SKU」列（用于列举真实SKU池）")

    c_match = _resolve_output_column(sku_headers, SKU_OUT_MATCH_ALIASES, "匹配SKU")
    c_approx = _resolve_output_column(sku_headers, SKU_OUT_APPROX_ALIASES, "近似匹配")
    c_qty = _resolve_output_column(sku_headers, SKU_OUT_QTY_ALIASES, "数量")
    c_status = _resolve_output_column(sku_headers, SKU_OUT_STATUS_ALIASES, "匹配状态")
    c_fail = _resolve_output_column(sku_headers, SKU_OUT_FAIL_ALIASES, "失败原因")
    c_audit = _resolve_output_column(sku_headers, SKU_OUT_AUDIT_ALIASES, "匹配审计")

    norm_to_canon, pool_display = _build_winit_pool_impl(sku_rows, col_real)
    if not norm_to_canon:
        raise ValueError(
            "「万邑通SKU」列中没有任何非空值，无法构建真实SKU池；请在同表该列列举全部真实SKU"
        )
    logger.info("万邑通SKU池: %s 个唯一SKU", len(norm_to_canon))

    out: list[dict[str, Any]] = []
    for row in sku_rows:
        base: dict[str, Any] = {k: row.get(k, "") for k in sku_headers}
        acc = row.get(col_acc)
        label = row.get(col_label)
        acc_str = str(acc).strip() if acc is not None else ""
        label_str = str(label).strip() if label is not None else ""

        base.setdefault(c_match, "")
        base.setdefault(c_approx, "")
        base.setdefault(c_qty, "")
        base.setdefault(c_status, "")
        base.setdefault(c_fail, "")
        base.setdefault(c_audit, "")

        if not acc_str:
            base[c_status] = "失败"
            base[c_fail] = "店铺账号为空"
            base[c_audit] = "NO_ACCOUNT"
            out.append(base)
            continue

        shorts = full_to_shorts.get(acc_str)
        if not shorts:
            base[c_status] = "失败"
            base[c_fail] = f"配对表中找不到店铺全称/账号「{acc_str}」"
            base[c_audit] = "NO_SHOP_PREFIX"
            out.append(base)
            continue

        if not label_str:
            base[c_status] = "失败"
            base[c_fail] = "Custom Label 为空"
            base[c_audit] = "EMPTY_LABEL"
            out.append(base)
            continue

        qty = parse_qty(label_str)
        candidates = collect_row_candidates(label_str, shorts)

        hit_norms: set[str] = set()
        for c in candidates:
            nk = normalize_real_sku(c)
            if nk in norm_to_canon:
                hit_norms.add(nk)

        if len(hit_norms) == 1:
            nk0 = next(iter(hit_norms))
            base[c_match] = norm_to_canon[nk0]
            base[c_qty] = qty
            base[c_approx] = ""
            base[c_status] = "成功"
            base[c_fail] = ""
            base[c_audit] = f"EXACT;pool={len(norm_to_canon)};candidates={candidates[:6]}"
            out.append(base)
            continue

        if len(hit_norms) > 1:
            base[c_match] = ""
            base[c_qty] = qty
            base[c_approx] = ""
            base[c_status] = "失败"
            base[c_fail] = f"精确匹配到多个万邑通SKU（歧义）：{[norm_to_canon[k] for k in sorted(hit_norms)][:5]}"
            base[c_audit] = f"AMBIGUOUS_EXACT;hits={len(hit_norms)}"
            out.append(base)
            continue

        # 无精确命中：对每个候选做保守近似匹配，仅接受全局唯一最佳
        fuzzy_hits: set[str] = set()
        for c in candidates:
            f = fuzzy_best_canonical(normalize_real_sku(c), norm_to_canon)
            if f:
                fuzzy_hits.add(f)
        if len(fuzzy_hits) == 1:
            base[c_match] = ""
            base[c_qty] = qty
            base[c_approx] = next(iter(fuzzy_hits))
            base[c_status] = "成功"
            base[c_fail] = ""
            base[c_audit] = f"FUZZY;pool={len(norm_to_canon)};candidates={candidates[:6]}"
            out.append(base)
            continue

        base[c_match] = ""
        base[c_qty] = qty
        base[c_approx] = ""
        base[c_status] = "失败"
        if len(fuzzy_hits) > 1:
            base[c_fail] = f"近似匹配结果不唯一：{sorted(fuzzy_hits)[:5]}"
            base[c_audit] = "AMBIGUOUS_FUZZY"
        else:
            base[c_fail] = "未在万邑通SKU池中找到精确匹配，且近似匹配未达置信阈值"
            base[c_audit] = f"NO_HIT;candidates={candidates[:8]}"
        out.append(base)

    return out
