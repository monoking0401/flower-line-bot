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

REGIONS = OrderedDict([
    ("雙北", [
        "台北", "臺北", "新北", "新店", "板橋", "中和", "永和",
        "三重", "蘆洲", "新莊", "土城", "樹林", "汐止", "淡水",
        "林口", "士林", "北投", "內湖", "南港", "松山", "信義",
        "大安", "中山", "中正", "萬華", "文山"
    ]),
    ("桃園", [
        "桃園", "中壢", "楊梅", "平鎮", "龜山", "八德", "蘆竹",
        "盧竹", "大溪", "龍潭", "大園", "觀音", "新屋"
    ]),
    ("新竹", [
        "新竹", "竹北", "湖口", "新豐", "竹東", "芎林",
        "關西", "新埔", "寶山"
    ]),
    ("中部", [
        "苗栗", "頭份", "竹南", "台中", "臺中", "彰化", "南投",
        "員林", "鹿港", "沙鹿", "大甲", "通霄", "苑裡",
        "豐原", "潭子", "大里", "烏日", "西屯", "北屯", "南屯"
    ]),
    ("雲嘉", [
        "雲林", "斗六", "虎尾", "嘉義", "民雄", "太保", "朴子"
    ]),
    ("台南", [
        "台南", "臺南", "新營", "永康", "新市", "善化", "安定"
    ]),
    ("高雄", [
        "高雄", "小港", "左營", "鳳山", "岡山", "楠梓"
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
        "新竹縣竹北市縣政八街58號",
        "新竹",
        True,
    ),
    "台中集貨站": (
        "台中市南屯區大墩十一街846號",
        "中部",
        True,
    ),
    "台灣造花": (
        "台中市南屯區大墩十一街846號",
        "中部",
        True,
    ),
    "彰化集貨站": (
        "彰化市中華西路216號",
        "中部",
        True,
    ),
    "新竹新馥": (
        "新竹市東區柴橋路139巷59-25號",
        "新竹",
        False,
    ),
    "新馥": (
        "新竹市東區柴橋路139巷59-25號",
        "新竹",
        False,
    ),
}

FLAGS = [
    "急件",
    "特快",
    "特別勤務",
]

PHONE_RE = re.compile(
    r"(?<!\d)(?:09\d{8}|0[2-8]\d{7,8})(?!\d)"
)

QTY_RE = re.compile(
    r"(\d{1,3})\s*(件|盆)"
)

BUCKET_RE = re.compile(
    r"(\d{1,3})\s*桶"
)

END_RE = re.compile(
    r"(?:(?:第?\s*(\d+)\s*趟)\s*)?"
    r"終點\s*[:：=]\s*"
    r"(桃園|新竹|中部|雲嘉|台南|高雄|雙北)"
)


def norm(s):
    return (
        s.replace("臺", "台")
        .replace("　", " ")
        .replace("／", "/")
        .strip()
    )


def region(s):
    t = norm(s)

    for name, words in REGIONS.items():
        if any(w in t for w in words):
            return name

    for road, name in ROAD_HINTS.items():
        if road in t:
            return name

    return None


def fixed(s):
    t = norm(s)

    for k in sorted(
        FIXED,
        key=len,
        reverse=True
    ):
        if k in t:
            return k, *FIXED[k]

    return None


def clean(s):
    for f in FLAGS:
        s = s.replace(f, "")

    return (
        PHONE_RE.sub("", s)
        .replace("🔺", "")
        .replace("▲", "")
        .strip(" /+-｜|")
    )


def strip_code(s):
    m = re.match(
        r"^#?.*?#(\d{4})(.+)$",
        s
    )

    if m:
        return (
            m.group(2).strip(),
            m.group(1),
        )

    m = re.match(
        r"^#?(\d{4})(.+)$",
        s
    )

    if m:
        return (
            m.group(2).strip(),
            m.group(1),
        )

    return (
        s.lstrip("#").strip(),
        None,
    )


def implicit_qty(body):
    matches = list(
        re.finditer(
            r"(?<!\d)(\d{1,3})(?!\d)",
            body
        )
    )

    for m in reversed(matches):
        after = body[m.end():]
        before = body[:m.start()]

        if re.match(
            r"\s*(號|段|巷|弄|樓|室|F|f)",
            after
        ):
            continue

        if before.rstrip().endswith("#"):
            continue

        if int(m.group(1)) == 0:
            continue

        if not re.search(
            r"[\u4e00-\u9fff]",
            before
        ):
            continue

        return m

    return None


def parse_line(line):
    raw = line.strip()

    if not raw:
        return None

    if (
        raw.upper() == "PT"
        or raw in {"正職", "模式"}
        or END_RE.search(raw)
    ):
        return None

    phones = PHONE_RE.findall(raw)

    no_phone = PHONE_RE.sub(
        " ",
        raw
    )

    body, code = strip_code(
        no_phone
    )

    prefix = ""

    if "/" in body:
        a, b = body.split("/", 1)

        if (
            (fixed(b) or region(b))
            and not any(
                x in a
                for x in
                "路街巷弄號站市縣區"
            )
        ):
            prefix = clean(a)
            body = b.strip()

    buckets = sum(
        int(m.group(1))
        for m in BUCKET_RE.finditer(body)
    )

    qs = list(
        QTY_RE.finditer(body)
    )

    qm = (
        qs[-1]
        if qs
        else implicit_qty(body)
    )

    if not qm:
        return None

    pieces = int(
        qm.group(1)
    )

    before = body[
        :qm.start()
    ].strip(" /+-")

    after = BUCKET_RE.sub(
        "",
        body[qm.end():]
    )

    recipient = (
        prefix
        or clean(after)
    )

    fx = fixed(before)

    if fx:
        loc, addr, rg, col = fx
    else:
        loc = before
        addr = before
        rg = region(before)

        col = (
            "集貨站" in before
            or "集運站" in before
        )

    return {
        "raw": raw,
        "code": code,
        "loc": loc,
        "addr": addr,
        "region": rg,
        "is_collection": col,
        "pieces": pieces,
        "buckets": buckets,
        "recipient": recipient,
        "phones": phones,
        "flags": [
            f
            for f in FLAGS
            if f in raw
        ],
    }


def parse_dispatch(text):
    endpoints = []

    for m in END_RE.finditer(text):
        trip = (
            int(m.group(1))
            if m.group(1)
            else None
        )

        endpoints.append({
            "trip": trip,
            "region": m.group(2),
        })

    items = []

    for line in text.splitlines():
        x = parse_line(line)

        if x:
            items.append(x)

    grouped = OrderedDict()

    for x in items:
        key = re.sub(
            r"[\s,，/#]",
            "",
            norm(x["addr"])
        ).lower()

        if key not in grouped:
            grouped[key] = {
                **x,
                "pieces": 0,
                "buckets": 0,
                "recipients": [],
                "phones": [],
                "flags": [],
            }

        s = grouped[key]

        s["pieces"] += x["pieces"]
        s["buckets"] += x["buckets"]

        if x["recipient"]:
            s["recipients"].append(
                x["recipient"]
            )

        for p in x["phones"]:
            if p not in s["phones"]:
                s["phones"].append(p)

        for f in x["flags"]:
            if f not in s["flags"]:
                s["flags"].append(f)

        if (
            not s["region"]
            and x["region"]
        ):
            s["region"] = x["region"]

    return (
        items,
        list(grouped.values()),
        endpoints,
    )


def calculate(text, mode):
    if mode not in {
        "PT",
        "正職"
    }:
        raise ValueError(
            "mode must be PT or 正職"
        )

    items, stops, endpoints = (
        parse_dispatch(text)
    )

    north = [
        s for s in stops
        if s["region"] == "雙北"
    ]

    general = [
        s for s in stops
        if s["region"] in BASE
    ]

    unknown = [
        s for s in stops
        if s["region"] is None
    ]

    lines = []
    warnings = []
    total = 0

    if north:
        p = len(north)

        n = sum(
            s["pieces"]
            for s in north
        )

        a = (
            p * NORTH_POINT_FEE
            + max(n - p, 0)
            * EXTRA_FEE
        )

        total += a

        lines.append({
            "name": "花市雙北",
            "amount": a,
            "desc": f"{p}點{n}件",
        })

    if general:
        p = len(general)

        n = sum(
            s["pieces"]
            for s in general
        )

        b = sum(
            s["buckets"]
            for s in general
        )

        a = (
            p * POINT_FEE
            + max(n - p, 0)
            * EXTRA_FEE
            + b * BUCKET_FEE
        )

        total += a

        desc = f"{p}點{n}件"

        if b:
            desc += f"＋{b}桶"

        lines.append({
            "name": "花市南",
            "amount": a,
            "desc": desc,
        })

    if endpoints:
        for i, ep in enumerate(
            endpoints,
            1
        ):
            if ep["region"] in BASE:
                a = BASE[
                    ep["region"]
                ]

                total += a

                if ep["trip"]:
                    label = (
                        f"第{ep['trip']}趟"
                    )
                else:
                    label = f"終點{i}"

                lines.append({
                    "name":
                    f"{label}打底"
                    f"（{ep['region']}）",
                    "amount": a,
                    "desc":
                    "依每趟終點計算",
                })

    elif mode == "PT":
        inferred = None

        for x in reversed(items):
            if (
                x["region"] in BASE
                and not x[
                    "is_collection"
                ]
            ):
                inferred = x[
                    "region"
                ]
                break

        if inferred:
            total += BASE[
                inferred
            ]

            lines.append({
                "name":
                f"PT推定終點打底"
                f"（{inferred}）",
                "amount":
                BASE[inferred],
                "desc":
                "未明寫終點，"
                "暫依最後一筆宅配推定",
            })

            warnings.append(
                "PT終點未明寫，"
                f"暫依最後一筆宅配"
                f"推定為「{inferred}」"
            )

    elif any(
        not s["is_collection"]
        for s in general
    ):
        warnings.append(
            "正職打底尚未明寫"
            "每趟終點；V2不再把"
            "沿途各區全部疊加。"
            "請加「第1趟終點=新竹」。"
        )

    for s in unknown:
        warnings.append(
            "地址區域待確認："
            f"{s['loc']}"
            "（不自動歸到花市南）"
        )

    for s in stops:
        if s["flags"]:
            warnings.append(
                f"{s['loc']}："
                f"{'/'.join(s['flags'])}"
                "（只標記，不自動加價）"
            )

    status = (
        "待確認"
        if unknown
        else "可估算"
    )

    if (
        mode == "正職"
        and not endpoints
        and any(
            not s["is_collection"]
            for s in general
        )
    ):
        status = "待確認打底"

    return {
        "mode": mode,
        "items": items,
        "stops": stops,
        "endpoints": endpoints,
        "lines": lines,
        "warnings": warnings,
        "total_points":
        len(stops),
        "total_pieces":
        sum(
            s["pieces"]
            for s in stops
        ),
        "total_buckets":
        sum(
            s["buckets"]
            for s in stops
        ),
        "total": total,
        "price_status":
        status,
    }


def format_result(r):
    out = [
        f"【花市智慧計算 V2｜"
        f"{r['mode']}】",

        f"總配送："
        f"{r['total_points']}點"
        f"{r['total_pieces']}件"
        + (
            f"｜{r['total_buckets']}桶"
            if r["total_buckets"]
            else ""
        ),

        f"狀態："
        f"{r['price_status']}",

        "",
        "配送整理：",
    ]

    for i, s in enumerate(
        r["stops"],
        1
    ):
        who = (
            "、".join(
                s["recipients"]
            )
            if s["recipients"]
            else "未標收件人"
        )

        col = (
            "【集貨/集運】"
            if s[
                "is_collection"
            ]
            else ""
        )

        line = (
            f"{i}. "
            f"{s['loc']}"
            f"{col}"
            f"｜"
            f"{s['region'] or '未知區域'}"
            f"｜"
            f"{s['pieces']}件"
        )

        if s["buckets"]:
            line += (
                f"＋"
                f"{s['buckets']}桶"
            )

        line += f"｜{who}"

        out.append(line)

    out += [
        "",
        "計價：",
    ]

    for x in r["lines"]:
        out.append(
            f"- {x['name']}："
            f"{x['amount']}元"
            f"（{x['desc']}）"
        )

    out += [
        "",
        f"目前可計金額："
        f"{r['total']:,}元"
    ]

    if r["warnings"]:
        out += [
            "",
            "提醒：",
        ]

        for x in r[
            "warnings"
        ]:
            out.append(
                f"- {x}"
            )

    return "\n".join(out)
