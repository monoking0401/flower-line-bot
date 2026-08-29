import os, re, json, hmac, hashlib, base64
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import holidays
from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI()
TZ = ZoneInfo("Asia/Taipei")

# Google Maps is intentionally disabled for now. The route helper remains ready
# so it can be enabled later without changing the LINE webhook contract.
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
    "九人座":2, "9人座":2, "8-9人座":2, "8～9人座":2,
    "七人座":2, "7人座":2,
    "九人座賓士":3, "VITO":3, "Vito":3, "賓士九人座":3,
}

ADDRESS_HINT = re.compile(r"(縣|市|區|鄉|鎮|村|里|路|街|巷|弄|號)")


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


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def detect_vehicle(text: str):
    for k, v in VEH_IDX.items():
        if k.lower() in text.lower():
            return k, v, True
    return "九人座", 2, False


def detect_people(text: str):
    patterns = [
        r"(?:乘客|人數|共)\s*[:：]?\s*(\d+)\s*人",
        r"(?<!\d)(\d+)\s*人(?!座)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def detect_luggage(text: str):
    m = re.search(r"(?:行李|大行李|件數)\s*[:：]?\s*(\d+)\s*(?:件|個)?", text)
    return int(m.group(1)) if m else None


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


def _find_datetime_near_label(text: str, label: str):
    m = re.search(
        rf"{re.escape(label)}[\s：:]*[^0-9\n]{{0,16}}"
        rf"(\d{{1,2}})[/-](\d{{1,2}})[^\d]{{0,16}}(\d{{1,2}})[:：](\d{{2}})",
        text,
        re.I,
    )
    if m:
        return make_dt(*map(int, m.groups()))

    m = re.search(
        rf"{re.escape(label)}[\s\S]{{0,50}}?"
        rf"(\d{{1,2}})[/-](\d{{1,2}})[\s\S]{{0,12}}?(\d{{1,2}})[:：](\d{{2}})",
        text,
        re.I,
    )
    return make_dt(*map(int, m.groups())) if m else None


def extract_labeled_datetime(text: str, labels):
    for label in labels:
        dt = _find_datetime_near_label(text, label)
        if dt:
            return dt
    return None


def parse_any_datetime(text: str):
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[\s\S]{0,20}?(\d{1,2})[:：](\d{2})", text)
    return make_dt(*map(int, m.groups())) if m else None


def extract_flight(text: str, label: str):
    m = re.search(rf"{re.escape(label)}[\s：:]*([A-Z]{{2}}\s?\d{{2,4}})", text, re.I)
    if not m:
        return None
    return m.group(1).replace(" ", "").upper()


def holiday_info(dt):
    if not dt:
        return False, None
    tw = holidays.Taiwan(years=[dt.year])
    return (dt.date() in tw, str(tw.get(dt.date())))


def _looks_like_address(line: str):
    if not line or len(line) < 5:
        return False
    if re.search(r"航班|報價|價格|車資|時間|起飛|抵達|人數|行李|九人座|七人座|五人座", line):
        return False
    if "機場接送" in line and not re.search(r"路|街|巷|弄|號", line):
        return False
    return bool(ADDRESS_HINT.search(line) and (re.search(r"\d", line) or "機場" in line or "高鐵站" in line))


def extract_addresses(text: str):
    raw_lines = [x.strip(" •-🔸📍①②③④⑤⑥⑦⑧⑨") for x in text.splitlines() if x.strip()]
    out = []
    for i, line in enumerate(raw_lines):
        if _looks_like_address(line):
            candidate = line
            if i + 1 < len(raw_lines):
                nxt = raw_lines[i + 1].strip()
                if (
                    len(nxt) <= 12
                    and re.search(r"號$", nxt)
                    and not re.search(r"縣|市|區|鄉|鎮|村|里|路|街|巷", nxt)
                    and not candidate.endswith("號")
                ):
                    candidate += nxt
            if candidate not in out:
                out.append(candidate)
    return out[:10]


def declared_point_count(text: str):
    cn = {"一":1, "二":2, "兩":2, "三":3, "四":4, "五":5, "六":6, "七":7, "八":8, "九":9}
    m = re.search(r"([1-9])\s*個?點", text)
    if m:
        return int(m.group(1))
    m = re.search(r"([一二兩三四五六七八九])\s*個?點", text)
    return cn.get(m.group(1)) if m else None


def has_taoyuan_airport_context(text: str):
    if any(k in text for k in ["桃機", "桃園機場", "桃園國際機場"]):
        return True
    return "桃園" in text and any(k in text for k in ["機場", "送機", "接機", "航班", "出國"])


def add_surcharges(base: int, dt, pickup: bool):
    total = base
    extras = []
    pending = []

    if pickup:
        total += 200
        extras.append(("接機", 200))

    if dt:
        if 0 <= dt.hour < 6:
            total += 200
            extras.append(("夜間", 200))
        if dt.weekday() >= 5:
            total += 200
            extras.append(("六日", 200))
        h, name = holiday_info(dt)
        if h:
            pending.append(f"國定假日 {name}：另議")

    return total, extras, pending


def money_lines(title, base, total, extras, pending, dt=None, flight=None, multipoint_count=1):
    lines = [title]
    if dt:
        lines.append(f"📅 {dt.strftime('%Y/%m/%d %H:%M')}")
    if flight:
        lines.append(f"✈️ {flight}")
    lines.append(f"基本車資：${base:,}")
    for name, val in extras:
        lines.append(f"{name}：+${val:,}")
    if multipoint_count >= 2:
        lines.append(f"多點接送：{multipoint_count}點（加價待確認）")
    for note in pending:
        lines.append(note)
    lines.append(f"小計：${total:,}" + ("＋多點待確認" if multipoint_count >= 2 else ""))
    return lines


def missing_info_reply(missing, parsed=None):
    lines = ["⚠️ 資料還不夠，我先不亂報價。"]
    if parsed:
        lines.append("")
        lines.append("目前已辨識：")
        lines.extend(parsed)
    lines.append("")
    lines.append("請補：" + "、".join(missing))
    lines.append("")
    lines.append("可直接回：")
    lines.append("報價")
    lines.append("日期時間：")
    lines.append("起點：")
    lines.append("終點：桃園機場")
    lines.append("接機/送機：")
    lines.append("車型或人數/行李：")
    return "\n".join(lines)


def ambiguity_warnings(send_service_dt, send_flight_dt):
    warnings = []
    if send_service_dt and send_flight_dt:
        diff_hours = (send_flight_dt - send_service_dt).total_seconds() / 3600
        if diff_hours > 12 or diff_hours < 0:
            warnings.append("⚠️ 送機上車時間與航班時間相差超過12小時，請確認日期是否正確。")
    return warnings


async def google_route(addresses):
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not MAPS_ENABLED or not key or len(addresses) < 2:
        return None
    inter = [{"address": a} for a in addresses[1:-1]]
    body = {
        "origin": {"address": addresses[0]},
        "destination": {"address": addresses[-1]},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "intermediates": inter,
        "optimizeWaypointOrder": bool(inter),
        "languageCode": "zh-TW",
        "units": "METRIC",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.optimizedIntermediateWaypointIndex",
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://routes.googleapis.com/directions/v2:computeRoutes", headers=headers, json=body)
        print("[MAPS]", r.status_code, r.text[:300], flush=True)
        if r.status_code != 200:
            return None
        routes = r.json().get("routes", [])
        if not routes:
            return None
        rr = routes[0]
        secs = int(str(rr.get("duration", "0s")).rstrip("s") or 0)
        return {"km": round(rr.get("distanceMeters", 0) / 1000, 1), "minutes": round(secs / 60)}


async def build_reply(text: str):
    text = clean_text(text)

    if text.strip() in {"幫助", "說明", "help", "HELP", "報價幫助"}:
        return (
            "🤖 小天智慧報價\n"
            "群組訊息只要包含「報價」兩個字才會觸發。\n"
            "可以直接貼客人原文，不必重打固定格式；資料不足時我才會請你補。"
        )

    if not has_taoyuan_airport_context(text):
        return (
            "⚠️ 目前自動客報先支援桃園機場正式價目。\n"
            "可直接貼完整客人訊息；只要內容有桃園/桃機＋送機、接機、航班或機場語意即可。"
        )

    area = detect_area(text)
    addresses = extract_addresses(text)
    local_addresses = [a for a in addresses if "機場" not in a]
    declared = declared_point_count(text)
    multipoint_count = max(len(local_addresses), declared or 0, 1)

    has_send = any(k in text for k in ["送機航班", "送機時間", "送機", "出發到桃園"])
    has_pick = any(k in text for k in ["接機航班", "接機時間", "接機", "落地"])
    roundtrip = has_send and has_pick

    people = detect_people(text)
    luggage = detect_luggage(text)
    vehicle, idx, vehicle_explicit = detect_vehicle(text)

    if not area:
        return missing_info_reply(["出發/目的地區域或完整地址"])

    parsed = [f"📍 地區：{area}"]
    if roundtrip:
        parsed.append("🔁 行程：送機＋接機")
    elif has_pick:
        parsed.append("✈️ 行程：接機")
    elif has_send:
        parsed.append("✈️ 行程：送機")

    if multipoint_count >= 2:
        parsed.append(f"📌 多點：{multipoint_count}點")
    if people is not None:
        parsed.append(f"👤 人數：{people}")
    if luggage is not None:
        parsed.append(f"🧳 行李：{luggage}")

    if not has_send and not has_pick:
        return missing_info_reply(["接機或送機"], parsed)

    base = TAOYUAN_PRICES[area][idx]

    lines = ["🤖 小天智慧報價", f"🚐 {vehicle}"]
    if not vehicle_explicit:
        if people is None:
            lines.append("ℹ️ 未提供車型/人數，先以九人座試算")
        elif people >= 5:
            lines.append("ℹ️ 依人數先以九人座試算")
        else:
            lines.append("ℹ️ 未提供車型，暫以九人座試算")

    if roundtrip:
        send_service_dt = extract_labeled_datetime(text, ["送機時間", "送機上車時間", "上車時間", "出發時間"])
        send_flight_dt = extract_labeled_datetime(text, ["送機航班"])
        pickup_service_dt = extract_labeled_datetime(text, ["接機時間", "接機上車時間"])
        pickup_flight_dt = extract_labeled_datetime(text, ["接機航班"])
        send_dt = send_service_dt or send_flight_dt
        pickup_dt = pickup_service_dt or pickup_flight_dt

        missing = []
        if not send_dt:
            missing.append("送機日期/時間")
        if not pickup_dt:
            missing.append("接機日期/時間")
        if missing:
            return missing_info_reply(missing, parsed)

        send_flight = extract_flight(text, "送機航班")
        pickup_flight = extract_flight(text, "接機航班")

        out_total, out_extras, out_pending = add_surcharges(base, send_dt, False)
        back_total, back_extras, back_pending = add_surcharges(base, pickup_dt, True)
        grand = out_total + back_total

        lines.append(f"📍 {area} ⇄ 桃園機場")
        if multipoint_count >= 2:
            lines.append(f"📌 已辨識 {multipoint_count} 個接送點")

        lines.append("")
        lines += money_lines(
            "【送機】", base, out_total, out_extras, out_pending,
            dt=send_dt, flight=send_flight, multipoint_count=multipoint_count
        )
        lines.append("")
        lines += money_lines(
            "【接機】", base, back_total, back_extras, back_pending,
            dt=pickup_dt, flight=pickup_flight, multipoint_count=multipoint_count
        )
        lines.append("")
        suffix = "＋多點加價待確認" if multipoint_count >= 2 else ""
        if out_pending or back_pending:
            suffix += "＋假日另議"
        lines.append(f"💰 來回目前試算：${grand:,}{suffix}")

        warnings = ambiguity_warnings(send_service_dt, send_flight_dt)
        if warnings:
            lines.append("")
            lines.extend(warnings)

        return "\n".join(lines)

    dt_labels = ["接機時間", "接機上車時間"] if has_pick else ["送機時間", "送機上車時間", "上車時間", "出發時間"]
    dt = extract_labeled_datetime(text, dt_labels)
    if not dt:
        dt = parse_any_datetime(text)
    if not dt:
        return missing_info_reply(["日期/時間"], parsed)

    pickup = has_pick and not has_send
    total, extras, pending = add_surcharges(base, dt, pickup)
    direction = f"桃園機場 → {area}" if pickup else f"{area} → 桃園機場"

    lines.append(f"📍 {direction}")
    if multipoint_count >= 2:
        lines.append(f"📌 已辨識 {multipoint_count} 個接送點")
    lines.append(f"📅 {dt.strftime('%Y/%m/%d %H:%M')}")
    lines.append(f"基本車資：${base:,}")
    for name, val in extras:
        lines.append(f"{name}：+${val:,}")
    if multipoint_count >= 2:
        lines.append(f"多點接送：{multipoint_count}點（加價待確認）")
    for note in pending:
        lines.append(note)

    suffix = "＋多點加價待確認" if multipoint_count >= 2 else ""
    if pending:
        suffix += "＋假日另議"
    lines.append(f"💰 目前試算：${total:,}{suffix}")
    return "\n".join(lines)


@app.get("/")
@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "xiaotian-quote-bot",
        "maps": False,
        "group_trigger": "contains:報價",
        "parser": "smart-v2",
    }


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
