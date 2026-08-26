import re
from collections import OrderedDict

POINT_FEE = 200
EXTRA_FEE = 100
BUCKET_FEE = 50
NORTH_POINT_FEE = 135

BASE = {
    "桃園": 100,
    "新竹": 300,
    "中部": 500,
    "雲嘉": 600,
    "台南": 800,
    "高雄": 1000,
}

SOUTH_ORDER = {
    "桃園": 1,
    "新竹": 2,
    "中部": 3,
    "雲嘉": 4,
    "台南": 5,
    "高雄": 6,
}

REGIONS = OrderedDict([
    ("雙北", [
        "台北", "臺北", "新北", "新店", "板橋", "中和", "永和",
        "三重", "蘆洲", "新莊", "土城", "樹林", "汐止", "淡水",
        "林口", "士林", "北投", "內湖", "南港", "松山", "信義",
        "大安", "中山", "中正", "萬華", "文山",
    ]),
    ("桃園", [
        "桃園", "中壢", "楊梅", "平鎮", "龜山", "八德", "蘆竹",
        "盧竹", "大溪", "龍潭", "大園", "觀音", "新屋",
    ]),
    ("新竹", [
        "新竹", "竹北", "湖口", "新豐", "竹東", "芎林",
        "關西", "新埔", "寶山",
    ]),
    ("中部", [
        "苗栗", "頭份", "竹南", "台中", "臺中", "彰化", "南投",
        "員林", "鹿港", "沙鹿", "大甲", "通霄", "苑裡",
        "豐原", "潭子", "大里", "烏日", "西屯", "北屯", "南屯",
    ]),
    ("雲嘉", [
        "雲林", "斗六", "虎尾", "嘉義", "民雄", "太保", "朴子",
    ]),
    ("台南", [
        "台南", "臺南", "新營", "永康", "新市", "善化", "安定",
    ]),
    ("高雄", [
        "高雄", "小港", "左營", "鳳山", "岡山", "楠梓",
    ]),
])

ROAD_HINTS = {
    "忠孝東路": "雙北",
    "南京東路": "雙北",
    "民生東路": "雙北",
    "信義路": "雙北",
    "仁愛路": "雙北",
    "復興南路": "雙北",
    "復興北路": "雙北",
    "市民大道": "雙北",
    "八德路": "雙北",
}

FIXED = {
    "竹北集貨站": (
        "新竹縣竹北市縣政八街58號", "新竹", True,
    ),
    "竹北縣政八街58號": (
        "新竹縣竹北市縣政八街58號", "新竹", True,
    ),
    "竹北縣政八街": (
        "新竹縣竹北市縣政八街58號", "新竹", True,
    ),
    "台中集貨站": (
        "台中市南屯區大墩十一街846號", "中部", True,
    ),
    "台灣造花": (
        "台中市南屯區大墩十一街846號", "中部", True,
    ),
    "彰化集貨站": (
        "彰化市中華西路216號", "中部", True,
    ),
    "新竹新馥": (
        "新竹市東區柴橋路139巷59-25號", "新竹", False,
    ),
    "新馥": (
        "新竹市東區柴橋路139巷59-25號", "新竹", False,
    ),
}

FLAGS = ["急件", "特快", "特別勤務"]
PHONE_RE = re.compile(r"(?<!\d)(?:09\d{8}|0[2-8]\d{7,8})(?!\d)")
QTY_RE = re.compile(r"(\d{1,3})\s*(件|盆)")
BUCKET_RE = re.compile(r"(\d{1,3})\s*桶")
END_RE = re.compile(
    r"(?:(?:第?\s*(\d+)\s*趟)\s*)?"
    r"終點\s*[:：=]\s*"
    r"(桃園|新竹|中部|雲嘉|台南|高雄|雙北)"
)
EXPLICIT_ADD_RE = re.compile(
    r"(?:特別勤務|加給)\s*[:：=]\s*(\d{1,5})"
)
TRANSFER_RE = re.compile(r"/\s*花市中轉\s*[-－]\s*(.+)$")
EXTRA_RE = re.compile(r"\+\s*(\d{1,3})\s*\*?\s*超(?:件)?")
RECEIVE_RE = re.compile(r"收\s*(\d{1,3})\s*(?:件|盆|高架)?")
TIME_LIMIT_RE = re.compile(
    r"(?:🔺|▲)?\s*限\s*\d{1,2}\s*(?:點|時)?\s*前"
)
TIME_WORD_RE = re.compile(
    r"(?:🔺|▲)?\s*(?:上午|中午|下午|晚上)?\s*\d{1,2}"
    r"\s*(?:點|時)\s*前|(?:🔺|▲)?\s*(?:中午|下午|晚上)前"
)


def norm(s):
    return (
        s.replace("臺", "台")
        .replace("　", " ")
        .replace("／", "/")
        .replace("－", "-")
        .strip()
    )


def region(s):
    t = norm(s)
    for name, words in REGIONS.items():
        if any(word in t for word in words):
            return name
    for road, name in ROAD_HINTS.items():
        if road in t:
            return name
    return None


def fixed(s):
    t = norm(s)
    for key in sorted(FIXED, key=len, reverse=True):
        if key in t:
            return key, *FIXED[key]
    return None


def _strip_annotations(s):
    s = PHONE_RE.sub(" ", s)
    s = TIME_LIMIT_RE.sub(" ", s)
    s = TIME_WORD_RE.sub(" ", s)
    for flag in FLAGS:
        s = s.replace(flag, " ")
    return (
        re.sub(r"\s+", " ", s)
        .replace("🔺", " ")
        .replace("▲", " ")
        .strip(" /+-｜|")
    )


def _source_family(source):
    s = _strip_annotations(source).lstrip("#").strip(" /+-")
    if not s:
        return ""
    match = re.match(r"([A-Za-z]+)", s)
    if match:
        return match.group(1).upper()
    return re.sub(r"[#\s/+-]", "", s)


def _split_source_code_body(raw):
    s = raw.lstrip("#").strip()

    match = re.match(r"(.+?)#(\d{4})(.+)$", s)
    if match:
        return (
            match.group(1).strip(" /"),
            match.group(2),
            match.group(3).strip(),
        )

    match = re.match(r"(\d{4})(.+)$", s)
    if match:
        return "", match.group(1), match.group(2).strip()

    if "/" in s:
        left, right = s.rsplit("/", 1)
        if fixed(right) or region(right):
            return left.strip(" /"), None, right.strip()

    return "", None, s


def _implicit_primary(body):
    matches = list(re.finditer(r"(?<!\d)(\d{1,3})(?!\d)", body))

    for match in reversed(matches):
        before = body[:match.start()]
        after = body[match.end():]

        if re.match(r"\s*(號|段|巷|弄|樓|室|F|f|前|點|時)", after):
            continue
        if before.rstrip().endswith("#"):
            continue
        if re.search(r"限\s*$", before):
            continue
        if int(match.group(1)) <= 0:
            continue
        if not re.search(r"[\u4e00-\u9fff]", before):
            continue

        return match

    return None


def _parse_transfer(raw, no_phone):
    transfer = TRANSFER_RE.search(no_phone)
    if not transfer:
        return None

    left = no_phone[:transfer.start()].strip()
    dest = transfer.group(1).strip()

    source = left.lstrip("#").split("+收", 1)[0].strip(" /+-")
    source = re.sub(r"#\d{4}.*$", "", source).strip(" /+-")

    receives = [int(value) for value in RECEIVE_RE.findall(left)]
    extras = [int(value) for value in EXTRA_RE.findall(left)]
    pieces = sum(receives) + sum(extras)

    if pieces <= 0:
        return None

    buckets = sum(
        int(match.group(1)) for match in BUCKET_RE.finditer(left)
    )

    dest_clean = _strip_annotations(dest)
    fx = fixed(dest_clean)

    if fx:
        loc, addr, rg, collection = fx
    else:
        loc = dest_clean
        addr = dest_clean
        rg = region(dest_clean)
        collection = "集貨站" in dest_clean or "集運站" in dest_clean

    return {
        "raw": raw,
        "code": None,
        "loc": loc,
        "addr": addr,
        "region": rg,
        "is_collection": collection,
        "pieces": pieces,
        "buckets": buckets,
        "recipient": source,
        "source_family": _source_family(source),
        "phones": PHONE_RE.findall(raw),
        "flags": [flag for flag in FLAGS if flag in raw],
        "is_transfer": True,
    }


def parse_line(line):
    raw = line.strip()

    if not raw:
        return None

    if raw.upper() == "PT" or raw in {"正職", "模式"} or END_RE.search(raw):
        return None

    if not raw.startswith("#") and not QTY_RE.search(raw) and "收" not in raw:
        return None

    no_phone = PHONE_RE.sub(" ", raw)

    transfer = _parse_transfer(raw, no_phone)
    if transfer:
        return transfer

    source, code, body = _split_source_code_body(no_phone)

    buckets = sum(
        int(match.group(1)) for match in BUCKET_RE.finditer(body)
    )

    quantity_matches = list(QTY_RE.finditer(body))

    if quantity_matches:
        quantity_match = quantity_matches[-1]
        pieces = int(quantity_match.group(1))
    else:
        quantity_match = _implicit_primary(body)
        if not quantity_match:
            return None

        pieces = int(quantity_match.group(1))
        pieces += sum(
            int(value)
            for value in EXTRA_RE.findall(body[quantity_match.end():])
        )

    before = body[:quantity_match.start()].strip(" /+-")
    after = body[quantity_match.end():]
    after = BUCKET_RE.sub(" ", after)
    after = EXTRA_RE.sub(" ", after)
    after = _strip_annotations(after)

    recipient = _strip_annotations(source) or after
    fx = fixed(before)

    if fx:
        loc, addr, rg, collection = fx
    else:
        loc = _strip_annotations(before)
        addr = loc
        rg = region(loc)
        collection = "集貨站" in loc or "集運站" in loc

    return {
        "raw": raw,
        "code": code,
        "loc": loc,
        "addr": addr,
        "region": rg,
        "is_collection": collection,
        "pieces": pieces,
        "buckets": buckets,
        "recipient": recipient,
        "source_family": _source_family(source),
        "phones": PHONE_RE.findall(raw),
        "flags": [flag for flag in FLAGS if flag in raw],
        "is_transfer": False,
    }


def _addr_key(addr):
    return re.sub(r"[\s,，/#\-]", "", norm(addr)).lower()


def _has_house_number(addr):
    return bool(re.search(r"\d+\s*號", norm(addr)))


def _group_key(item, index):
    address_key = _addr_key(item["addr"])

    if item["is_collection"] or fixed(item["addr"]):
        return "fixed", address_key

    family = item.get("source_family", "")
    if family:
        return "family", family, address_key

    if _has_house_number(item["addr"]):
        return "address", address_key

    # 老闆派單常只寫到路名。同路名可能實際是不同門牌，
    # 沒有可靠共同識別時寧可分點，避免錯誤合併。
    return "unique", index


def parse_dispatch(text):
    endpoints = []

    for match in END_RE.finditer(text):
        endpoints.append({
            "trip": int(match.group(1)) if match.group(1) else None,
            "region": match.group(2),
        })

    items = []
    for line in text.splitlines():
        parsed = parse_line(line)
        if parsed:
            items.append(parsed)

    grouped = OrderedDict()

    for index, item in enumerate(items):
        key = _group_key(item, index)

        if key not in grouped:
            grouped[key] = {
                **item,
                "pieces": 0,
                "buckets": 0,
                "recipients": [],
                "phones": [],
                "flags": [],
                "is_transfer": False,
            }

        stop = grouped[key]
        stop["pieces"] += item["pieces"]
        stop["buckets"] += item["buckets"]
        stop["is_transfer"] = stop["is_transfer"] or item.get(
            "is_transfer", False
        )

        if item["recipient"] and item["recipient"] not in stop["recipients"]:
            stop["recipients"].append(item["recipient"])

        for phone in item["phones"]:
            if phone not in stop["phones"]:
                stop["phones"].append(phone)

        for flag in item["flags"]:
            if flag not in stop["flags"]:
                stop["flags"].append(flag)

        if not stop["region"] and item["region"]:
            stop["region"] = item["region"]

    return items, list(grouped.values()), endpoints


def _southmost_delivery_region(stops):
    regions = [
        stop["region"]
        for stop in stops
        if not stop["is_collection"] and stop["region"] in BASE
    ]

    if not regions:
        return None

    return max(regions, key=lambda name: SOUTH_ORDER[name])


def calculate(text, mode):
    if mode not in {"PT", "正職"}:
        raise ValueError("mode must be PT or 正職")

    items, stops, endpoints = parse_dispatch(text)

    north = [stop for stop in stops if stop["region"] == "雙北"]
    general = [stop for stop in stops if stop["region"] in BASE]
    unknown = [stop for stop in stops if stop["region"] is None]

    lines = []
    warnings = []
    total = 0

    if north:
        points = len(north)
        pieces = sum(stop["pieces"] for stop in north)
        amount = (
            points * NORTH_POINT_FEE
            + max(pieces - points, 0) * EXTRA_FEE
        )
        total += amount
        lines.append({
            "name": "花市雙北",
            "amount": amount,
            "desc": f"{points}點{pieces}件",
        })

    if general:
        points = len(general)
        pieces = sum(stop["pieces"] for stop in general)
        buckets = sum(stop["buckets"] for stop in general)
        amount = (
            points * POINT_FEE
            + max(pieces - points, 0) * EXTRA_FEE
            + buckets * BUCKET_FEE
        )
        total += amount

        desc = f"{points}點{pieces}件"
        if buckets:
            desc += f"＋{buckets}桶"

        lines.append({
            "name": "花市南",
            "amount": amount,
            "desc": desc,
        })

    if endpoints:
        for index, endpoint in enumerate(endpoints, 1):
            if endpoint["region"] not in BASE:
                continue

            amount = BASE[endpoint["region"]]
            total += amount
            label = (
                f"第{endpoint['trip']}趟"
                if endpoint["trip"]
                else f"終點{index}"
            )
            lines.append({
                "name": f"{label}打底（{endpoint['region']}）",
                "amount": amount,
                "desc": "依每趟終點計算",
            })

    elif mode == "PT":
        inferred = _southmost_delivery_region(stops)
        if inferred:
            amount = BASE[inferred]
            total += amount
            lines.append({
                "name": f"PT推定終點打底（{inferred}）",
                "amount": amount,
                "desc": "依南下宅配最南端推定",
            })
            warnings.append(
                f"PT終點未明寫，依南下宅配最南端推定為「{inferred}」"
            )

    elif any(not stop["is_collection"] for stop in general):
        warnings.append(
            "正職打底需要依該趟實際／公司指定終點計算；"
            "本訊息未明寫終點，因此不猜、不疊加各區打底。"
            "請補「終點=新竹」或「第1趟終點=中部」。"
        )

    explicit_adds = [int(value) for value in EXPLICIT_ADD_RE.findall(text)]
    if explicit_adds:
        amount = sum(explicit_adds)
        total += amount
        lines.append({
            "name": "明確其他加給",
            "amount": amount,
            "desc": "依訊息明寫金額",
        })

    if any(stop.get("is_transfer") for stop in stops):
        warnings.append(
            "偵測到「花市中轉／收貨」派單：已按實際送達點計入點件；"
            "其特別勤務加給不是固定值，未明寫金額時不自動猜。"
        )

    for stop in unknown:
        warnings.append(
            f"地址區域待確認：{stop['loc']}（不自動歸到花市南）"
        )

    for stop in stops:
        if stop["flags"]:
            warnings.append(
                f"{stop['loc']}：{'/'.join(stop['flags'])}"
                "（只標記，不自動加價）"
            )

    status = "待確認" if unknown else "可估算"

    if (
        mode == "正職"
        and not endpoints
        and any(not stop["is_collection"] for stop in general)
    ):
        status = "待確認打底"

    return {
        "mode": mode,
        "items": items,
        "stops": stops,
        "endpoints": endpoints,
        "lines": lines,
        "warnings": warnings,
        "total_points": len(stops),
        "total_pieces": sum(stop["pieces"] for stop in stops),
        "total_buckets": sum(stop["buckets"] for stop in stops),
        "total": total,
        "price_status": status,
    }


def format_result(result):
    out = [
        f"【花市智慧計算 V3｜{result['mode']}】",
        (
            f"總配送：{result['total_points']}點{result['total_pieces']}件"
            + (
                f"｜{result['total_buckets']}桶"
                if result["total_buckets"]
                else ""
            )
        ),
        f"狀態：{result['price_status']}",
        "",
        "配送整理：",
    ]

    for index, stop in enumerate(result["stops"], 1):
        who = (
            "、".join(stop["recipients"])
            if stop["recipients"]
            else "未標收件人"
        )
        collection = "【集貨/集運】" if stop["is_collection"] else ""
        line = (
            f"{index}. {stop['loc']}{collection}｜"
            f"{stop['region'] or '未知區域'}｜{stop['pieces']}件"
        )
        if stop["buckets"]:
            line += f"＋{stop['buckets']}桶"
        line += f"｜{who}"
        out.append(line)

    out += ["", "計價："]

    for item in result["lines"]:
        out.append(
            f"- {item['name']}：{item['amount']}元（{item['desc']}）"
        )

    out += ["", f"目前可計金額：{result['total']:,}元"]

    if result["warnings"]:
        out += ["", "提醒:"]
        out += [f"- {warning}" for warning in result["warnings"]]

    return "\n".join(out)
