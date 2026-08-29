import os, re, json, hmac, hashlib, base64
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import holidays
from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI()
TZ = ZoneInfo("Asia/Taipei")
MAPS_ENABLED = False

TAOYUAN_PRICES = {
    "宜蘭市以北": [2100,2200,2500,3500], "宜蘭市以南": [2200,2300,2600,3600],
    "蘇澳": [2600,2700,3200,4200], "花蓮市區": [5100,5200,5700,6700],
    "花蓮山區": [5600,5700,6200,7200], "基隆": [1300,1400,1800,2800],
    "金山萬里": [1700,1800,2000,3000], "三芝": [1500,1600,1800,2800],
    "淡水": [1200,1300,1500,2500], "新北市": [1000,1100,1400,1900],
    "台北市": [1000,1100,1400,1900], "桃園市區以內": [800,900,1100,1600],
    "桃園市區以外": [900,1000,1300,1800], "新竹市區": [1200,1300,1600,2600],
    "新竹香山竹東": [1300,1400,1700,2700], "苗栗": [1600,1700,1900,2900],
    "苗栗銅鑼": [1900,2000,2200,3200], "台中": [2200,2300,2500,3500],
    "台中烏日": [2300,2400,2600,3600], "台中霧峰": [2400,2500,2700,3700],
    "彰化埔鹽以北": [2700,2800,3000,4000], "彰化埔鹽以南": [2800,2900,3100,4100],
    "草屯": [3000,3100,3300,4300], "埔里": [3800,3900,4100,5100],
    "日月潭": [4000,4100,4300,5300], "清境": [4500,4600,4800,5800],
    "雲林": [3800,3900,4100,5100], "嘉義": [4000,4100,4300,5300],
    "台南": [5000,5100,5300,6300], "高雄": [6000,6100,6300,7300],
    "屏東": [6500,6600,6800,7800], "墾丁": [7500,7600,7800,8800],
    "台東": [9000,9100,9300,10300],
}

VEH_IDX = {
    "五人轎車":0, "5人轎車":0, "五人座":0, "5人座":0,
    "五人休旅":1, "5人休旅":1, "休旅":1,
    "九人座":2, "9人座":2, "8-9人座":2, "七人座":2, "7人座":2,
    "九人座賓士":3, "VITO":3, "Vito":3, "賓士九人座":3,
}


def valid_signature(raw: bytes, sig: str) -> bool:
    secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if not secret or not sig:
        return False
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), sig)


async def line_reply(token: str, text: str):
    access = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not access:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN missing")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
            json={"replyToken": token, "messages": [{"type": "text", "text": text[:4900]}]},
        )
        print("[LINE]", r.status_code, r.text, flush=True)
        r.raise_for_status()


def detect_vehicle(text: str):
    for k, v in VEH_IDX.items():
        if k.lower() in text.lower():
            return k, v, True
    return "九人座", 2, False


def detect_area(text: str):
    rules = [
        ("墾丁", ["墾丁", "恆春"]), ("清境", ["清境"]), ("日月潭", ["日月潭"]),
        ("埔里", ["埔里"]), ("草屯", ["草屯"]), ("台東", ["台東"]),
        ("花蓮山區", ["太魯閣", "壽豐", "瑞穗", "玉里"]), ("花蓮市區", ["花蓮"]),
        ("屏東", ["屏東"]), ("高雄", ["高雄"]), ("台南", ["台南"]),
        ("嘉義", ["嘉義"]), ("雲林", ["雲林"]),
        ("彰化埔鹽以南", ["埔鹽", "溪湖", "田中", "北斗", "田尾", "二林", "員林"]),
        ("彰化埔鹽以北", ["彰化", "花壇", "和美", "鹿港", "伸港"]),
        ("台中霧峰", ["霧峰"]), ("台中烏日", ["烏日"]), ("台中", ["台中"]),
        ("苗栗銅鑼", ["銅鑼"]), ("苗栗", ["苗栗", "竹南", "頭份"]),
        ("新竹香山竹東", ["香山", "竹東"]), ("新竹市區", ["新竹"]),
        ("淡水", ["淡水"]), ("三芝", ["三芝"]), ("金山萬里", ["金山", "萬里"]),
        ("基隆", ["基隆"]), ("新北市", ["新北"]), ("台北市", ["台北"]),
        ("桃園市區以內", ["桃園", "中壢", "平鎮", "八德"]),
    ]
    for area, kws in rules:
        if any(k in text for k in kws):
            return area
    return None


def infer_year(month: int, day: int):
    now = datetime.now(TZ)
    return now.year if (month, day) >= (now.month, now.day) else now.year + 1


def make_dt(month: int, day: int, hour: int, minute: int):
    try:
        return datetime(infer_year(month, day), month, day, hour, minute, tzinfo=TZ)
    except ValueError:
        return None


def extract_labeled_datetime(text: str, labels):
    for label in labels:
        m = re.search(
            rf"{re.escape(label)}[^\n]*?(\d{{1,2}})[/-](\d{{1,2}})[^\n]*?(\d{{1,2}})[:：](\d{{2}})",
            text,
            re.I,
        )
        if m:
            return make_dt(*map(int, m.groups()))
    return None


def parse_any_datetime(text: str):
    m = re.search(r"(\d{1,2})[/-](\d{1,2}).{0,20}?(\d{1,2})[:：](\d{2})", text, re.S)
    if not m:
        return None
    return make_dt(*map(int, m.groups()))


def holiday_info(dt):
    if not dt:
        return False, None
    tw = holidays.Taiwan(years=[dt.year])
    return (dt.date() in tw, str(tw.get(dt.date())))


def extract_addresses(text):
    lines = [x.strip(" •-🔸📍①②③④⑤⑥⑦⑧⑨") for x in text.splitlines() if x.strip()]
    out = []
    for x in lines:
        if re.search(r"(縣|市|區|鄉|鎮|路|街|巷|號|機場|高鐵站)", x) and not re.search(
            r"車資|航班|報價|基本車資|價格|時間", x
        ):
            if x not in out:
                out.append(x)
    return out[:10]


def has_taoyuan_airport_context(text: str):
    if any(k in text for k in ["桃機", "桃園機場", "桃園國際機場"]):
        return True
    return "桃園" in text and any(k in text for k in ["機場", "送機", "接機", "航班", "出國"])


def add_surcharges(base: int, dt, pickup: bool, multipoint: bool):
    total = base
    extras = []
    if pickup:
        total += 200
        extras.append(("接機等候", 200))
    if dt:
        if 0 <= dt.hour < 6:
            total += 200
            extras.append(("夜間", 200))
        if dt.weekday() >= 5:
            total += 200
            extras.append(("六日", 200))
        h, name = holiday_info(dt)
        if h:
            extras.append((f"國定假日 {name}", "另議"))
    if multipoint:
        total += 200
        extras.append(("多點接送", 200))
    return total, extras


def money_lines(title, base, total, extras, dt=None):
    lines = [title]
    if dt:
        lines.append(f"📅 {dt.strftime('%Y/%m/%d %H:%M')}")
    lines.append(f"基本車資：${base:,}")
    for name, val in extras:
        lines.append(f"{name}：+${val:,}" if isinstance(val, int) else f"{name}：{val}")
    lines.append(f"小計：${total:,}")
    return lines


async def build_reply(text):
    if text.strip() in {"幫助", "說明", "help", "HELP", "報價幫助"}:
        return "🤖 小天AI報價\n群組訊息只要包含『報價』兩個字才會觸發。\n可直接貼客人完整訊息，再加上『報價』。"

    if not has_taoyuan_airport_context(text):
        return "⚠️ 試算版目前先支援桃園機場正式價目。\n訊息可寫『桃園機場』，或像『埔里出發到桃園＋送機/接機航班』也能辨識。"

    area = detect_area(text)
    if not area:
        return "⚠️ 找不到出發/目的地區域，請補上地區或完整地址後再報價。"

    vehicle, idx, vehicle_explicit = detect_vehicle(text)
    base = TAOYUAN_PRICES[area][idx]
    addresses = extract_addresses(text)
    local = [a for a in addresses if "機場" not in a]
    multipoint = len(local) >= 3 or "三個點" in text or "3個點" in text

    has_send = any(k in text for k in ["送機航班", "送機時間", "送機"])
    has_pick = any(k in text for k in ["接機航班", "接機時間", "接機", "落地"])
    roundtrip = has_send and has_pick

    lines = ["🤖 小天AI報價", f"🚐 {vehicle}"]
    if not vehicle_explicit:
        lines.append("ℹ️ 未指定車型，先以九人座試算")

    if roundtrip:
        send_service_dt = extract_labeled_datetime(text, ["送機時間", "出發時間", "上車時間"])
        send_flight_dt = extract_labeled_datetime(text, ["送機航班"])
        pickup_flight_dt = extract_labeled_datetime(text, ["接機航班", "接機時間"])

        out_total, out_extras = add_surcharges(base, send_service_dt or send_flight_dt, False, multipoint)
        back_total, back_extras = add_surcharges(base, pickup_flight_dt, True, multipoint)
        grand = out_total + back_total

        lines.append(f"📍 {area} ⇄ 桃園機場")
        lines.append("")
        lines += money_lines("【送機】", base, out_total, out_extras, send_service_dt or send_flight_dt)
        lines.append("")
        lines += money_lines("【接機】", base, back_total, back_extras, pickup_flight_dt)
        lines.append("")
        lines.append(f"💰 來回試算：${grand:,}")

        if send_service_dt and send_flight_dt:
            diff_hours = (send_flight_dt - send_service_dt).total_seconds() / 3600
            if diff_hours > 12 or diff_hours < 0:
                lines.append("⚠️ 送機上車時間與航班時間相差超過12小時，請確認日期是否輸入正確。")
        return "\n".join(lines)

    dt = extract_labeled_datetime(text, ["送機時間", "接機時間", "上車時間", "出發時間"])
    if not dt:
        dt = parse_any_datetime(text)
    pickup = has_pick and not has_send
    total, extras = add_surcharges(base, dt, pickup, multipoint)
    direction = f"桃園機場 → {area}" if pickup else f"{area} → 桃園機場"
    lines.append(f"📍 {direction}")
    if dt:
        lines.append(f"📅 {dt.strftime('%Y/%m/%d %H:%M')}")
    lines.append(f"基本車資：${base:,}")
    for name, val in extras:
        lines.append(f"{name}：+${val:,}" if isinstance(val, int) else f"{name}：{val}")
    lines.append(f"💰 建議客報：${total:,}")
    return "\n".join(lines)


@app.get("/")
@app.get("/health")
async def health():
    return {"ok": True, "service": "xiaotian-quote-bot", "maps": False}


@app.post("/webhook")
async def webhook(req: Request, x_line_signature: str | None = Header(default=None)):
    raw = await req.body()
    if not valid_signature(raw, x_line_signature or ""):
        raise HTTPException(401, "Invalid signature")
    body = json.loads(raw)
    for ev in body.get("events", []):
        if ev.get("type") != "message" or ev.get("message", {}).get("type") != "text":
            continue
        text = ev["message"].get("text", "").strip()
        source = ev.get("source", {}).get("type")
        if source in {"group", "room"} and "報價" not in text:
            continue
        if "報價" in text:
            text = text.replace("報價", "", 1).strip()
        token = ev.get("replyToken")
        if token:
            try:
                await line_reply(token, await build_reply(text))
            except Exception as exc:
                print("[ERR]", repr(exc), flush=True)
    return {"ok": True}
