import re
from collections import OrderedDict

try:
    from .flower_engine_v2 import (
        BASE,
        POINT_FEE,
        EXTRA_FEE,
        BUCKET_FEE,
        NORTH_POINT_FEE,
        FIXED,
        PHONE_RE,
        parse_dispatch as _parse_dispatch,
        format_result,
    )
except ImportError:
    from flower_engine_v2 import (
        BASE,
        POINT_FEE,
        EXTRA_FEE,
        BUCKET_FEE,
        NORTH_POINT_FEE,
        FIXED,
        PHONE_RE,
        parse_dispatch as _parse_dispatch,
        format_result,
    )

SOUTH_ORDER = {
    "桃園": 1,
    "新竹": 2,
    "中部": 3,
    "雲嘉": 4,
    "台南": 5,
    "高雄": 6,
}

DEADLINE_RE = re.compile(
    r"(?:🔺|▲)?\s*(?:限\s*)?\d{1,2}(?::\d{2})?\s*(?:點|時)?\s*前"
)

PICKUP_RE = re.compile(
    r"收\s*(\d{1,3})\s*(?:件|盆|高架)?"
    r"(?:\s*\+\s*(\d{1,3})\s*\*?\s*超(?:件)?)?"
)


def _norm(s):
    return (
        s.replace("臺", "台")
        .replace("　", " ")
        .replace("／", "/")
        .replace("－", "-")
        .strip()
    )


def _key(s):
    return re.sub(r"[\s,，/#\-]", "", _norm(s)).lower()


def _named_prefix(raw):
    m = re.match(r"^#?(.+?)#\d{4}", raw)
    if not m:
        return ""
    p = m.group(1).strip(" #/+")
    if p in {"TJ", "TJ/"}:
        return "TJ"
    return p


def _is_fixed_stop(item):
    canonical = {v[0].replace("臺", "台") for v in FIXED.values()}
    return _norm(item["addr"]) in canonical or item["loc"] in FIXED


def _has_house_number(item):
    if _is_fixed_stop(item):
        return True
    return bool(re.search(r"\d+\s*號", _norm(item["addr"])))


def _source_label(left):
    t = left.strip()
    t = re.sub(r"^#?[^#]*#\d{4}", "", t)
    t = re.sub(r"^#?", "", t)
    t = PICKUP_RE.sub("", t)
    return t.strip(" +-/") or "花市中轉"


def _preprocess(text):
    """Normalize special pickup/transfer syntax before the legacy parser.

    Examples:
    收2+1*超件/花市中轉-新竹東區北大路 -> 3件
    收1盆/花市中轉-苗栗頭份中央路🔺限12前 -> 1件
    """
    out = []

    for raw in text.splitlines():
        line = DEADLINE_RE.sub("", raw)

        if "/花市中轉" not in line and "／花市中轉" not in line:
            out.append(line)
            continue

        normalized = line.replace("／", "/")
        left, right = normalized.split("/", 1)

        if "花市中轉" not in right:
            out.append(line)
            continue

        m = PICKUP_RE.search(left)
        if not m:
            out.append(line)
            continue

        qty = int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)
        dest = re.sub(r"^花市中轉\s*[-:：]?\s*", "", right).strip()
        dest = DEADLINE_RE.sub("", dest).replace("🔺", "").replace("▲", "").strip()
        label = _source_label(left)

        # Synthetic code keeps the existing parser stable. The marker remains
        # in raw so the regrouping layer knows this is an add-on to a stop.
        out.append(f"#9999{dest}{qty}{label}花市中轉")

    return "\n".join(out)


def _rebuild_stops(items):
    grouped = OrderedDict()
    base_candidates = {}

    for idx, item in enumerate(items):
        bkey = _key(item["addr"])
        transfer = "花市中轉" in item["raw"]

        if transfer:
            candidates = base_candidates.get(bkey, [])
            if len(candidates) == 1:
                gkey = candidates[0]
            else:
                gkey = f"{bkey}|transfer|{idx}"
        elif _is_fixed_stop(item) or _has_house_number(item):
            gkey = bkey
        else:
            prefix = _named_prefix(item["raw"])
            if prefix:
                # Same named shop/source + same street is strong evidence of
                # one point (08/21 曾聰明花坊／楊梅自立街).
                gkey = f"{bkey}|prefix:{_key(prefix)}"
            else:
                # Street-only text is incomplete. Different recipients may be
                # different door numbers (08/19 光明六路兩個不同地址).
                gkey = f"{bkey}|line:{idx}"

        if gkey not in grouped:
            grouped[gkey] = {
                **item,
                "pieces": 0,
                "buckets": 0,
                "recipients": [],
                "phones": [],
                "flags": [],
            }
            base_candidates.setdefault(bkey, []).append(gkey)

        stop = grouped[gkey]
        stop["pieces"] += item["pieces"]
        stop["buckets"] += item["buckets"]

        recipient = item.get("recipient") or ""
        recipient = recipient.replace("花市中轉", "").strip(" /+-")
        if recipient and recipient not in stop["recipients"]:
            stop["recipients"].append(recipient)

        for phone in item.get("phones", []):
            if phone not in stop["phones"]:
                stop["phones"].append(phone)

        for flag in item.get("flags", []):
            if flag not in stop["flags"]:
                stop["flags"].append(flag)

        if transfer and "花市中轉" not in stop["flags"]:
            stop["flags"].append("花市中轉")

        if not stop.get("region") and item.get("region"):
            stop["region"] = item["region"]

    return list(grouped.values())


def _delivery_regions(stops):
    return [
        stop["region"]
        for stop in stops
        if not stop["is_collection"] and stop["region"] in BASE
    ]


def _price_points(stops):
    north = [s for s in stops if s["region"] == "雙北"]
    general = [s for s in stops if s["region"] in BASE]

    lines = []
    total = 0

    if north:
        p = len(north)
        n = sum(s["pieces"] for s in north)
        amount = p * NORTH_POINT_FEE + max(n - p, 0) * EXTRA_FEE
        total += amount
        lines.append({
            "name": "花市雙北",
            "amount": amount,
            "desc": f"{p}點{n}件",
        })

    if general:
        p = len(general)
        n = sum(s["pieces"] for s in general)
        b = sum(s["buckets"] for s in general)
        amount = (
            p * POINT_FEE
            + max(n - p, 0) * EXTRA_FEE
            + b * BUCKET_FEE
        )
        total += amount
        desc = f"{p}點{n}件" + (f"＋{b}桶" if b else "")
        lines.append({
            "name": "花市南",
            "amount": amount,
            "desc": desc,
        })

    return total, lines


def _add_pt_base(stops, total, lines, warnings):
    regions = _delivery_regions(stops)
    if not regions:
        return total

    region = max(regions, key=lambda name: SOUTH_ORDER[name])
    amount = BASE[region]
    lines.append({
        "name": f"PT終點打底（{region}）",
        "amount": amount,
        "desc": "每趟只計1個；排除集貨/集運後取南下最南端宅配區域",
    })
    warnings.append(f"PT打底：本趟最南宅配區域＝{region}")
    return total + amount


def _add_fulltime_base(stops, total, lines, warnings):
    regions = _delivery_regions(stops)
    if not regions:
        return total

    distinct = [name for name in BASE if name in regions]
    for region in distinct:
        amount = BASE[region]
        lines.append({
            "name": f"正職區域打底（{region}）",
            "amount": amount,
            "desc": "正職同一趟：每個實際宅配區域各計1次",
        })
        total += amount

    warnings.append(
        "正職打底：同一趟各實際宅配區域分別計1次；純集貨/集運不計"
    )
    return total


def calculate(text, mode):
    if mode not in {"PT", "正職"}:
        raise ValueError("mode must be PT or 正職")

    prepared = _preprocess(text)
    items, _old_stops, endpoints = _parse_dispatch(prepared)
    stops = _rebuild_stops(items)

    total, lines = _price_points(stops)
    warnings = []

    if endpoints:
        # Manual endpoint syntax stays available for exceptional cases.
        for i, ep in enumerate(endpoints, 1):
            region = ep["region"]
            if region in BASE:
                amount = BASE[region]
                label = f"第{ep['trip']}趟" if ep.get("trip") else f"終點{i}"
                lines.append({
                    "name": f"{label}打底（{region}）",
                    "amount": amount,
                    "desc": "依明寫終點手動指定",
                })
                total += amount
    elif mode == "PT":
        total = _add_pt_base(stops, total, lines, warnings)
    else:
        total = _add_fulltime_base(stops, total, lines, warnings)

    unknown = [s for s in stops if s["region"] is None]
    for stop in unknown:
        warnings.append(
            f"地址區域待確認：{stop['loc']}（不自動歸到花市南）"
        )

    seen_transfer_warning = set()
    for stop in stops:
        if "花市中轉" in stop["flags"]:
            k = _key(stop["loc"])
            if k not in seen_transfer_warning:
                warnings.append(
                    f"{stop['loc']}：花市中轉的送達點件已納入；"
                    "額外特別勤務加給不自動猜，等老闆正式日結"
                )
                seen_transfer_warning.add(k)

        other = [f for f in stop["flags"] if f != "花市中轉"]
        if other:
            warnings.append(
                f"{stop['loc']}：{'/'.join(other)}（只標記，不自動加價）"
            )

    incomplete_counts = {}
    for stop in stops:
        if not _is_fixed_stop(stop) and not _has_house_number(stop):
            k = _key(stop["addr"])
            incomplete_counts[k] = incomplete_counts.get(k, 0) + 1
    if any(v > 1 for v in incomplete_counts.values()):
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
