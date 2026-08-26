import os
import re
import json
import hmac
import hashlib
import base64
from collections import OrderedDict

import httpx
from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI()

STATE = {}

BASE = {
    "桃園": 100,
    "新竹": 300,
    "中部": 500,
    "雲嘉": 600,
    "台南": 800,
    "高雄": 1000,
}

REGIONS = OrderedDict([
    ("桃園", ["桃園", "中壢", "楊梅", "平鎮", "龜山", "八德", "蘆竹", "大溪", "龍潭", "大園", "觀音", "新屋"]),
    ("新竹", ["新竹", "竹北", "湖口", "新豐", "竹東", "芎林", "關西", "新埔", "寶山"]),
    ("中部", ["苗栗", "頭份", "竹南", "台中", "臺中", "彰化", "南投", "員林", "鹿港", "沙鹿", "大甲"]),
    ("雲嘉", ["雲林", "斗六", "虎尾", "嘉義", "民雄", "太保", "朴子"]),
    ("台南", ["台南", "臺南", "新營", "永康", "新市", "善化", "安定"]),
    ("高雄", ["高雄", "小港", "左營", "鳳山", "岡山", "楠梓"]),
])

NORTH = [
    "台北", "臺北", "新北", "新店", "板橋", "中和", "永和",
    "三重", "蘆洲", "新莊", "土城", "樹林", "汐止", "淡水", "林口"
]

FIX = {
    "竹北集貨站": ("新竹縣竹北市縣政八街58號", "新竹", True),
    "台中集貨站": ("台中市南屯區大墩十一街846號", "中部", True),
    "台灣造花": ("台中市南屯區大墩十一街846號", "中部", True),
    "彰化集貨站": ("彰化市中華西路216號", "中部", True),
    "新竹新馥": ("新竹市東區柴橋路139巷59-25號", "新竹", False),
    "新馥": ("新竹市東區柴橋路139巷59-25號", "新竹", False),
}

FLAGS = ["急件", "特快", "特別勤務"]


def region(s):
    if any(x in s for x in NORTH):
        return "雙北"

    for r, words in REGIONS.items():
        if any(x in s for x in words):
            return r

    return None


def fixed(s):
    for k in sorted(FIX, key=len, reverse=True):
        if k in s:
            return k, *FIX[k]

    return None


def clean(s):
    for f in FLAGS:
        s = s.replace(f, "")

    return (
        s.replace("🔺", "")
        .replace("▲", "")
        .strip(" /+-")
    )


def one(tok):
    raw = tok.strip()
    t = raw.lstrip("#").strip()

    m = re.match(r"(.+?)#\d{4}(.+)$", t)
    if m:
        body = m.group(2).strip()
    else:
        m = re.match(r"\d{4}(.+)$", t)
        body = m.group(1).strip() if m else t

    rec0 = ""

    if "/" in body:
        a, b = body.split("/", 1)

        if (
            (region(b) or fixed(b))
            and not any(x in a for x in "路街巷站市縣")
        ):
            rec0 = clean(a)
            body = b.strip()

    qty_matches = list(re.finditer(r"(\d+)\s*(件|盆)", body))
    buckets = 0

    if qty_matches:
        m = qty_matches[-1]
        pieces = int(m.group(1))
        span = m.span()

        bm = re.search(r"(\d+)\s*桶", body)
        buckets = int(bm.group(1)) if bm else 0

    else:
        candidates = list(
            re.finditer(
                r"(\d+)(?=$|(?:/|🔺|▲|[A-Za-z\u4e00-\u9fff]))",
                body
            )
        )

        m = candidates[-1] if candidates else None

        if not m:
            return None

        pieces = int(m.group(1))
        span = m.span()

    before = body[:span[0]].strip(" /+-")

    after = re.sub(
        r"\+?\s*\d+\s*桶",
        "",
        body[span[1]:]
    )

    rec = rec0 or clean(after)

    fx = fixed(before)

    if fx:
        loc, addr, rg, col = fx
    else:
        loc = before
        addr = before
        rg = region(before)
        col = "集貨站" in before or "集運站" in before

    return {
        "raw": raw,
        "loc": loc,
        "addr": addr,
        "rg": rg,
        "col": col,
        "cat": "雙北" if rg == "雙北" else "南",
        "pieces": pieces,
        "buckets": buckets,
        "rec": rec,
        "flags": [f for f in FLAGS if f in raw],
    }


def parse(text):
    items = []

    for line in text.splitlines():
        tok = line.strip()

        if not tok:
            continue

        if tok.upper() == "PT" or tok == "正職":
            continue

        if tok.startswith("終點"):
            continue

        if (
            tok.startswith("#")
            or re.search(r"\d+\s*(件|盆|桶)", tok)
        ):
            x = one(tok)

            if x:
                items.append(x)

    grouped = OrderedDict()

    for x in items:
        key = re.sub(
            r"[\s　,，/／#]",
            "",
            x["addr"]
        ).lower()

        if key not in grouped:
            grouped[key] = {
                **x,
                "pieces": 0,
                "buckets": 0,
                "recs": [],
                "flags": [],
            }

        stop = grouped[key]
        stop["pieces"] += x["pieces"]
        stop["buckets"] += x["buckets"]

        if x["rec"]:
            stop["recs"].append(x["rec"])

        for f in x["flags"]:
            if f not in stop["flags"]:
                stop["flags"].append(f)

    epm = re.search(
        r"終點\s*[:：=]\s*(桃園|新竹|中部|雲嘉|台南|高雄|雙北)",
        text
    )

    endpoint = epm.group(1) if epm else None

    return items, list(grouped.values()), endpoint


def calc(text, mode):
    items, stops, endpoint = parse(text)

    total = 0
    lines = []
    warnings = []

    north_stops = [
        s for s in stops
        if s["cat"] == "雙北"
    ]

    south_stops = [
        s for s in stops
        if s["cat"] != "雙北"
    ]

    if north_stops:
        points = len(north_stops)
        pieces = sum(s["pieces"] for s in north_stops)

        amount = (
            points * 135
            + max(pieces - points, 0) * 100
        )

        total += amount

        lines.append(
            (
                "花市雙北",
                amount,
                f"{points}點{pieces}件"
            )
        )

    if south_stops:
        points = len(south_stops)
        pieces = sum(s["pieces"] for s in south_stops)
        buckets = sum(s["buckets"] for s in south_stops)

        amount = (
            points * 200
            + max(pieces - points, 0) * 100
            + buckets * 50
        )

        total += amount

        desc = f"{points}點{pieces}件"

        if buckets:
            desc += f"＋{buckets}桶"

        lines.append(
            ("花市南", amount, desc)
        )

    if mode == "PT" and any(
        not s["col"] for s in south_stops
    ):
        if not endpoint:
            for x in reversed(items):
                if x["rg"] and x["rg"] != "雙北":
                    endpoint = x["rg"]
                    break

        if endpoint in BASE:
            total += BASE[endpoint]

            lines.append(
                (
                    f"PT終點打底（{endpoint}）",
                    BASE[endpoint],
                    "每趟只算最終區域1次"
                )
            )

            if "終點" not in text:
                warnings.append(
                    f"PT終點未明寫，依最後一筆派單推定為「{endpoint}」"
                )
        else:
            warnings.append(
                "⚠️ PT無法判斷終點，請加：終點=新竹"
            )

    if mode == "正職":
        regs = []

        for s in south_stops:
            if (
                not s["col"]
                and s["rg"] in BASE
                and s["rg"] not in regs
            ):
                regs.append(s["rg"])

        for r in regs:
            total += BASE[r]

            lines.append(
                (
                    f"正職區域打底（{r}）",
                    BASE[r],
                    "正職與PT分開"
                )
            )

    for s in stops:
        if s["flags"]:
            warnings.append(
                f"{s['loc']}：{'/'.join(s['flags'])}"
                "（只標記，不自動加價）"
            )

    out = [
        f"【花市自動計算｜{mode}】",
        f"總配送：{len(stops)}點"
        f"{sum(s['pieces'] for s in stops)}件",
        "",
        "配送整理：",
    ]

    for i, s in enumerate(stops, 1):
        rec = (
            "、".join(s["recs"])
            if s["recs"]
            else "未標收件人"
        )

        out.append(
            f"{i}. {s['loc']}"
            f"{'【集貨/集運】' if s['col'] else ''}"
            f"｜{s['pieces']}件｜{rec}"
        )

    out += ["", "計價："]

    for name, amount, desc in lines:
        out.append(
            f"- {name}：{amount}元（{desc}）"
        )

    out += [
        "",
        f"預估日結：{total:,}元"
    ]

    if warnings:
        out += [
            "",
            "提醒：",
            *[f"- {x}" for x in warnings]
        ]

    return "\n".join(out)


def source_id(event):
    source = event.get("source", {})

    return (
        source.get("groupId")
        or source.get("roomId")
        or source.get("userId")
        or "unknown"
    )


def valid(raw, signature):
    secret = os.getenv(
        "LINE_CHANNEL_SECRET",
        ""
    )

    if not secret or not signature:
        return False

    digest = hmac.new(
        secret.encode(),
        raw,
        hashlib.sha256
    ).digest()

    expected = base64.b64encode(
        digest
    ).decode()

    return hmac.compare_digest(
        expected,
        signature
    )


async def reply(token, text):
    access_token = os.getenv(
        "LINE_CHANNEL_ACCESS_TOKEN",
        ""
    )

    print(
        "[REPLY] access token exists =",
        bool(access_token),
        "| length =",
        len(access_token),
        flush=True
    )

    if not access_token:
        print(
            "[REPLY] ERROR: LINE_CHANNEL_ACCESS_TOKEN is empty",
            flush=True
        )

        raise RuntimeError(
            "LINE_CHANNEL_ACCESS_TOKEN is empty"
        )

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "replyToken": token,
                "messages": [
                    {
                        "type": "text",
                        "text": text[:4900],
                    }
                ],
            },
        )

        print(
            "[REPLY] LINE status =",
            response.status_code,
            flush=True
        )

        print(
            "[REPLY] LINE body =",
            response.text,
            flush=True
        )

        response.raise_for_status()


@app.get("/")
@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "flower-line-bot",
    }


@app.post("/webhook")
async def webhook(
    req: Request,
    x_line_signature: str | None = Header(default=None),
):
    raw = await req.body()

    print(
        "\n========== WEBHOOK RECEIVED ==========",
        flush=True
    )

    print(
        "[WEBHOOK] signature exists =",
        bool(x_line_signature),
        flush=True
    )

    if not valid(raw, x_line_signature or ""):
        print(
            "[WEBHOOK] INVALID SIGNATURE",
            flush=True
        )

        raise HTTPException(
            401,
            "Invalid signature"
        )

    body = json.loads(raw)

    events = body.get("events", [])

    print(
        "[WEBHOOK] event count =",
        len(events),
        flush=True
    )

    for event in events:
        print(
            "---------- EVENT ----------",
            flush=True
        )

        print(
            "[EVENT] type =",
            event.get("type"),
            flush=True
        )

        print(
            "[EVENT] mode =",
            event.get("mode"),
            flush=True
        )

        print(
            "[EVENT] replyToken exists =",
            bool(event.get("replyToken")),
            flush=True
        )

        print(
            "[EVENT] source type =",
            event.get("source", {}).get("type"),
            flush=True
        )

        if event.get("type") != "message":
            print(
                "[EVENT] skip: not message",
                flush=True
            )
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            print(
                "[EVENT] skip: not text",
                flush=True
            )
            continue

        text = message.get("text", "").strip()

        token = event.get("replyToken")

        sid = source_id(event)

        print(
            "[EVENT] text =",
            repr(text),
            flush=True
        )

        print(
            "[EVENT] sid =",
            sid,
            flush=True
        )

        if not token:
            print(
                "[EVENT] ERROR: no replyToken | mode =",
                event.get("mode"),
                flush=True
            )
            continue

        if text.upper() == "PT":
            print(
                "[COMMAND] PT detected",
                flush=True
            )

            STATE[sid] = "PT"

            await reply(
                token,
                "✅ 已切換為 PT 模式。"
            )

            print(
                "[COMMAND] PT reply sent",
                flush=True
            )

            continue

        if text == "正職":
            print(
                "[COMMAND] 正職 detected",
                flush=True
            )

            STATE[sid] = "正職"

            await reply(
                token,
                "✅ 已切換為 正職 模式。"
            )

            continue

        if text == "模式":
            await reply(
                token,
                "目前模式："
                f"{STATE.get(sid, '尚未設定')}"
            )

            continue

        first = next(
            (
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ),
            ""
        )

        if first.upper() == "PT":
            mode = "PT"
        elif first == "正職":
            mode = "正職"
        else:
            mode = STATE.get(sid)

        if (
            first.upper() == "PT"
            or first == "正職"
        ):
            STATE[sid] = mode

        if not mode:
            print(
                "[EVENT] skip: mode not set",
                flush=True
            )
            continue

        if (
            "#" not in text
            and not re.search(
                r"\d+\s*(件|盆)",
                text
            )
        ):
            print(
                "[EVENT] skip: no dispatch content",
                flush=True
            )
            continue

        result = calc(
            text,
            mode
        )

        print(
            "[CALC] sending result",
            flush=True
        )

        await reply(
            token,
            result
        )

    print(
        "========== WEBHOOK DONE ==========\n",
        flush=True
    )

    return {
        "ok": True
    }
