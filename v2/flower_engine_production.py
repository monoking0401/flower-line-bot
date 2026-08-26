import re

try:
    from . import flower_engine_pt_south as legacy
except ImportError:
    import flower_engine_pt_south as legacy


FLOOR_SERVICE_FEE = 100
FLOOR_SERVICE_RE = re.compile(r"(?:送\s*上樓|上\s*樓|樓層費|樓層)")

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


def calculate(text, mode):
    if mode not in {"PT", "正職"}:
        raise ValueError("mode must be PT or 正職")

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
