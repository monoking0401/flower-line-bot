import re
from collections import OrderedDict

try:
    from . import flower_engine_pt_south as legacy
except ImportError:
    import flower_engine_pt_south as legacy


FLOOR_SERVICE_FEE = 100
FLOOR_SERVICE_RE = re.compile(r"(?:送\s*上樓|上\s*樓|樓層費|樓層)")

# Settlement / day-end ledger detection.
# These messages contain money figures (100/300/500/170...) that must never be
# interpreted as implicit delivery quantities.
DATE_LINE_RE = re.compile(r"^\s*(\d{1,2}/\d{1,2})\s*(.*)$")
SETTLEMENT_HINT_RE = re.compile(
    r"(?:日結|小計|總計|代收|代墊|日配打底|"
    r"花市雙北\s*\d+\s*點|花市南\s*\d+\s*點|"
    r"特別勤務加給|收貨助理)"
)
SUMMARY_RE = re.compile(
    r"^\s*(小計|代收|代墊|總計)\s*[:：]?\s*\$?\s*([0-9,]+)"
)
AMOUNT_EXPR_AT_END_RE = re.compile(
    r"([+$]?\s*\d{1,6}(?:\s*\+\s*\d{1,6})*)\s*(?:元)?\s*$"
)
SEPARATOR_RE = re.compile(r"^[-—─_= ]{3,}$")

# When the city/area is explicitly at the front of the parsed address, prefer it
# over weaker substring matches in road names. Example:
# 新竹東區新北路 -> 新竹, not 雙北 merely because the road is named 新北路.
REGION_PREFIXES = [
    ("高雄", ("高雄", "小港", "左營", "鳳山", "岡山", "楠梓")),
    ("台南", ("台南", "新營", "永康", "新市", "善化", "安定")),
    ("雲嘉", ("雲林", "斗六", "虎尾", "嘉義", "民雄", "太保", "朴子")),
    ("中部", ("苗栗", "頭份", "竹南", "台中", "彰化", "南投", "員林", "鹿港", "沙鹿", "大甲", "通霄", "苑裡", "豐原", "潭子", "大里", "烏日", "西屯", "北屯", "南屯")),
    ("新竹", ("新竹", "竹北", "湖口", "新豐", "竹東", "芎林", "關西", "新埔", "寶山")),
    ("桃園", ("桃園", "中壢", "楊梅", "平鎮", "龜山", "八德", "蘆竹", "盧竹", "大溪", "龍潭", "大園", "觀音", "新屋")),
]


def _correct_region(addr, current):
    text = legacy._norm(addr or "")
    for region, prefixes in REGION_PREFIXES:
        if any(text.startswith(prefix) for prefix in prefixes):
            return region
    return current


def _strip_floor_service_annotations(text):
    return FLOOR_SERVICE_RE.sub("", text)


def _looks_like_settlement(text):
    dated = sum(
        1
        for line in text.splitlines()
        if DATE_LINE_RE.match(line.strip())
    )
    return dated >= 1 and bool(SETTLEMENT_HINT_RE.search(text))


def _eval_amount_expr(expr):
    nums = re.findall(r"\d{1,6}", expr.replace(",", ""))
    return sum(int(n) for n in nums)


def _dated_blocks(text):
    blocks = []
    current = None

    def flush():
        nonlocal current
        if current is not None:
            blocks.append(current)
            current = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = DATE_LINE_RE.match(line)
        if m:
            flush()
            current = {
                "date": m.group(1),
                "parts": [m.group(2).strip()],
            }
            continue

        if current is None:
            continue

        if (
            SUMMARY_RE.match(line)
            or line.startswith("$")
            or SEPARATOR_RE.fullmatch(line)
        ):
            flush()
            continue

        current["parts"].append(line)

    flush()
    return blocks


def _block_amount(block):
    body = " ".join(block["parts"]).strip()
    m = AMOUNT_EXPR_AT_END_RE.search(body)
    if not m:
        return None, body
    return _eval_amount_expr(m.group(1)), body


def _formula_expected(body):
    m = re.search(
        r"花市雙北\s*(\d+)\s*點\s*(\d+)\s*件",
        body,
    )
    if m:
        points = int(m.group(1))
        pieces = int(m.group(2))
        amount = (
            points * legacy.NORTH_POINT_FEE
            + max(pieces - points, 0) * legacy.EXTRA_FEE
        )
        return amount, f"花市雙北{points}點{pieces}件"

    m = re.search(
        r"花市南\s*(\d+)\s*點\s*(\d+)\s*件"
        r"(?:\s*(\d+)\s*桶)?",
        body,
    )
    if m:
        points = int(m.group(1))
        pieces = int(m.group(2))
        buckets = int(m.group(3) or 0)
        amount = (
            points * legacy.POINT_FEE
            + max(pieces - points, 0) * legacy.EXTRA_FEE
            + buckets * legacy.BUCKET_FEE
        )
        label = f"花市南{points}點{pieces}件"
        if buckets:
            label += f"{buckets}桶"
        return amount, label

    return None, None


def _parse_summary_values(text):
    out = {}
    for raw in text.splitlines():
        m = SUMMARY_RE.match(raw.strip())
        if m:
            out[m.group(1)] = int(m.group(2).replace(",", ""))
    return out


def _parse_settlement(text, mode):
    daily = OrderedDict()
    reimbursements = 0
    warnings = []
    corrections = []
    total_points = 0
    total_pieces = 0
    total_buckets = 0

    for block in _dated_blocks(text):
        amount, body = _block_amount(block)
        date = block["date"]

        if amount is None:
            warnings.append(
                f"{date} 無法讀取金額：{body}（已略過，不拿數字亂當件數）"
            )
            continue

        is_advance = "代墊" in body
        if is_advance:
            reimbursements += amount
        else:
            daily[date] = daily.get(date, 0) + amount

        expected, label = _formula_expected(body)
        if expected is not None and expected != amount:
            delta = expected - amount
            corrections.append({
                "date": date,
                "label": label,
                "written": amount,
                "expected": expected,
                "delta": delta,
            })
            warnings.append(
                f"{date} {label}：依目前公式應 {expected:,} 元，"
                f"原文寫 {amount:,} 元，差 {amount - expected:+,} 元"
            )

        m = re.search(
            r"花市(?:雙北|南)\s*(\d+)\s*點\s*(\d+)\s*件"
            r"(?:\s*(\d+)\s*桶)?",
            body,
        )
        if m:
            total_points += int(m.group(1))
            total_pieces += int(m.group(2))
            total_buckets += int(m.group(3) or 0)

    declared = _parse_summary_values(text)
    detail_subtotal = sum(daily.values())

    declared_advance = declared.get("代墊")
    advance = reimbursements
    if advance == 0 and declared_advance is not None:
        advance = declared_advance

    detail_total = detail_subtotal + advance
    formula_delta = sum(x["delta"] for x in corrections)
    formula_subtotal = detail_subtotal + formula_delta
    formula_total = formula_subtotal + advance

    if "小計" in declared and declared["小計"] != detail_subtotal:
        warnings.append(
            f"原文明細逐項加總是 {detail_subtotal:,} 元，"
            f"但原文小計寫 {declared['小計']:,} 元，"
            f"差 {declared['小計'] - detail_subtotal:+,} 元"
        )

    if (
        declared_advance is not None
        and reimbursements
        and declared_advance != reimbursements
    ):
        warnings.append(
            f"明細代墊 {reimbursements:,} 元，"
            f"原文代墊欄寫 {declared_advance:,} 元"
        )

    if "總計" in declared and declared["總計"] != detail_total:
        warnings.append(
            f"依原文明細＋代墊應為 {detail_total:,} 元，"
            f"但原文總計寫 {declared['總計']:,} 元，"
            f"差 {declared['總計'] - detail_total:+,} 元"
        )

    if declared.get("代收", 0):
        warnings.append(
            f"原文代收為 {declared['代收']:,} 元；"
            "代收如何沖帳未自動猜，請依老闆結算規則確認"
        )

    return {
        "kind": "settlement",
        "mode": mode,
        "items": [],
        "stops": [],
        "endpoints": [],
        "lines": [],
        "warnings": warnings,
        "total_points": total_points,
        "total_pieces": total_pieces,
        "total_buckets": total_buckets,
        "total": formula_total if corrections else detail_total,
        "price_status": "日結有差異待確認" if warnings else "日結驗算一致",
        "daily": list(daily.items()),
        "detail_subtotal": detail_subtotal,
        "advance": advance,
        "detail_total": detail_total,
        "formula_subtotal": formula_subtotal,
        "formula_total": formula_total,
        "corrections": corrections,
        "declared": declared,
    }


def calculate(text, mode):
    if mode not in {"PT", "正職"}:
        raise ValueError("mode must be PT or 正職")

    # Day-end settlement text must not enter the dispatch parser. The legacy
    # parser intentionally supports implicit quantities such as "新竹XX路2小王";
    # without this guard, money figures such as +500 or 170元 can become
    # hundreds of fake flower pieces.
    if _looks_like_settlement(text):
        return _parse_settlement(text, mode)

    has_floor_service = bool(FLOOR_SERVICE_RE.search(text))
    parse_text = _strip_floor_service_annotations(text)

    prepared = legacy._preprocess(parse_text)
    items, _old_stops, endpoints = legacy._parse_dispatch(prepared)

    # Correct weak substring-based region classification before regrouping and
    # before either PT or full-time base-fee logic runs.
    for item in items:
        item["region"] = _correct_region(item.get("addr"), item.get("region"))

    stops = legacy._rebuild_stops(items)
    total, lines = legacy._price_points(stops)
    warnings = []

    if endpoints:
        for i, ep in enumerate(endpoints, 1):
            region = ep["region"]
            if region in legacy.BASE:
                amount = legacy.BASE[region]
                label = f"第{ep['trip']}趟" if ep.get("trip") else f"終點{i}"
                lines.append({
                    "name": f"{label}打底（{region}）",
                    "amount": amount,
                    "desc": "依明寫終點手動指定",
                })
                total += amount
    elif mode == "PT":
        total = legacy._add_pt_base(stops, total, lines, warnings)
    else:
        total = legacy._add_fulltime_base(stops, total, lines, warnings)

    if has_floor_service:
        lines.append({
            "name": "樓層費",
            "amount": FLOOR_SERVICE_FEE,
            "desc": "本趟有送上樓／上樓／樓層費／樓層註記，整趟只加1次",
        })
        total += FLOOR_SERVICE_FEE

    unknown = [s for s in stops if s["region"] is None]
    for stop in unknown:
        warnings.append(
            f"地址區域待確認：{stop['loc']}（不自動歸到花市南）"
        )

    seen_transfer_warning = set()
    for stop in stops:
        if "花市中轉" in stop["flags"]:
            key = legacy._key(stop["loc"])
            if key not in seen_transfer_warning:
                warnings.append(
                    f"{stop['loc']}：花市中轉的送達點件已納入；"
                    "額外特別勤務加給不自動猜，等老闆正式日結"
                )
                seen_transfer_warning.add(key)

        other = [f for f in stop["flags"] if f != "花市中轉"]
        if other:
            warnings.append(
                f"{stop['loc']}：{'/'.join(other)}（只標記，不自動加價）"
            )

    incomplete_counts = {}
    for stop in stops:
        if not legacy._is_fixed_stop(stop) and not legacy._has_house_number(stop):
            key = legacy._key(stop["addr"])
            incomplete_counts[key] = incomplete_counts.get(key, 0) + 1
    if any(value > 1 for value in incomplete_counts.values()):
        warnings.append(
            "有同路名但未含完整門牌的多筆派單：先分開計點，避免把不同地址誤合併"
        )

    return {
        "mode": mode,
        "items": items,
        "stops": stops,
        "endpoints": endpoints,
        "lines": lines,
        "warnings": warnings,
        "total_points": len(stops),
        "total_pieces": sum(s["pieces"] for s in stops),
        "total_buckets": sum(s["buckets"] for s in stops),
        "total": total,
        "price_status": "待確認" if unknown else "可估算",
    }


def format_result(result):
    if result.get("kind") != "settlement":
        return legacy.format_result(result)

    out = [
        f"【花市日結驗算｜{result['mode']}】",
        f"狀態：{result['price_status']}",
        "",
        "每日明細加總：",
    ]

    for date, amount in result["daily"]:
        out.append(f"- {date}：{amount:,}元（未含代墊）")

    out += [
        "",
        f"原文明細小計：{result['detail_subtotal']:,}元",
        f"代墊：{result['advance']:,}元",
        f"依原文明細應付：{result['detail_total']:,}元",
    ]

    if result["corrections"]:
        out += [
            "",
            "依花市公式檢查：",
        ]
        for x in result["corrections"]:
            out.append(
                f"- {x['date']} {x['label']}："
                f"應{x['expected']:,}元／原文{x['written']:,}元"
            )
        out.append(
            f"依公式校正後應付：{result['formula_total']:,}元"
        )

    if result["declared"]:
        out += ["", "原文結算欄："]
        for key in ("小計", "代收", "代墊", "總計"):
            if key in result["declared"]:
                out.append(f"- {key}：{result['declared'][key]:,}元")

    if result["warnings"]:
        out += ["", "⚠️ 驗算提醒："]
        for warning in result["warnings"]:
            out.append(f"- {warning}")

    out += [
        "",
        "※ 日結文字中的+100/+300/+500/170元等金額，"
        "不再當成配送件數解析。"
    ]

    return "\n".join(out)
