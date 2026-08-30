import os, re, json, hmac, hashlib, base64
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import holidays
from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI()
TZ = ZoneInfo("Asia/Taipei")
MAPS_ENABLED = False

# 正式來源：小天包車旅遊｜完整報價資料庫＋雲端交接｜2026-08-01
# 一般車型欄位順序：五人轎車、五人休旅款、九人座、九人座賓士
AIRPORT_PRICES = {
    "桃園機場": {
        "宜蘭市以北":[2100,2200,2500,3500], "宜蘭市以南":[2200,2300,2600,3600],
        "蘇澳":[2600,2700,3200,4200], "花蓮市區":[5100,5200,5700,6700],
        "花蓮山區":[5600,5700,6200,7200], "基隆":[1300,1400,1800,2800],
        "金山萬里":[1700,1800,2000,3000], "三芝":[1500,1600,1800,2800],
        "淡水":[1200,1300,1500,2500], "新北市":[1000,1100,1400,1900],
        "台北市":[1000,1100,1400,1900], "桃園市區以內":[800,900,1100,1600],
        "桃園市區以外":[900,1000,1300,1800], "新竹市區":[1200,1300,1600,2600],
        "新竹香山竹東":[1300,1400,1700,2700], "苗栗":[1600,1700,1900,2900],
        "苗栗銅鑼":[1900,2000,2200,3200], "台中":[2200,2300,2500,3500],
        "台中烏日":[2300,2400,2600,3600], "台中霧峰":[2400,2500,2700,3700],
        "彰化埔鹽以北":[2700,2800,3000,4000], "彰化埔鹽以南":[2800,2900,3100,4100],
        "草屯":[3000,3100,3300,4300], "埔里":[3800,3900,4100,5100],
        "日月潭":[4000,4100,4300,5300], "清境":[4500,4600,4800,5800],
        "雲林":[3800,3900,4100,5100], "嘉義":[4000,4100,4300,5300],
        "台南":[5000,5100,5300,6300], "高雄":[6000,6100,6300,7300],
        "屏東":[6500,6600,6800,7800], "墾丁":[7500,7600,7800,8800],
        "台東":[9000,9100,9300,10300],
    },
    "松山機場": {
        "宜蘭市以北":[1600,1700,2200,3200], "宜蘭市以南":[1700,1800,2300,3300],
        "蘇澳":[2100,2200,2700,3700], "花蓮市區":[4600,4700,5200,6200],
        "花蓮山區":[5100,5200,5700,6700], "基隆":[1000,1100,1500,2500],
        "金山萬里":[1500,1600,1800,2800], "三芝":[1200,1300,1500,2500],
        "淡水":[1000,1100,1300,2300], "新北市":[800,900,1200,1700],
        "台北市":[800,900,1200,1700], "桃園市區以內":[1000,1100,1400,1900],
        "桃園市區以外":[1100,1200,1500,2000], "新竹市區":[1600,1700,2000,3000],
        "新竹香山竹東":[1700,1800,2100,3100], "苗栗":[2100,2200,2400,3400],
        "苗栗銅鑼":[2400,2500,2700,3700], "台中":[2700,2800,3000,4000],
        "台中烏日":[2800,2900,3100,4100], "台中霧峰":[2900,3000,3200,4200],
        "彰化埔鹽以北":[3200,3300,3500,4500], "彰化埔鹽以南":[3300,3400,3600,4600],
        "草屯":[3500,3600,3800,4800], "埔里":[4400,4500,4700,5700],
        "日月潭":[5000,5100,5300,6300], "清境":[4300,4400,4600,5600],
        "雲林":[4500,4600,4800,5800], "嘉義":[5500,5600,5800,6800],
        "台南":[6500,6600,6800,7800], "屏東":[7000,7100,7300,8300],
        "墾丁":[8000,8100,8300,9300], "台東":[9500,9600,9800,10800],
    },
    "台中清泉崗機場": {
        "宜蘭":[4300,4400,4900,5900], "基隆":[3500,3600,4000,5000],
        "台北":[2700,2800,3000,4000], "新北":[2800,2900,3100,4100],
        "桃園":[2200,2300,2500,3500], "新竹":[1900,2000,2200,3200],
        "苗栗":[1600,1700,1900,2900], "台中市區":[900,1000,1200,2200],
        "彰化市區":[1300,1400,1600,2600], "南投市／草屯":[1500,1600,1800,2800],
        "集集":[1900,2000,2200,3200], "埔里":[2000,2100,2300,3300],
        "雲林":[2300,2400,2600,3600], "嘉義":[2900,3000,3200,4200],
        "台南":[3500,3600,4000,5000], "高雄":[4000,4100,4500,5500],
        "屏東":[4500,4600,5000,6000], "恆春／墾丁":[6000,6100,6500,7500],
        "花蓮":[8500,8600,9000,10000], "台東":[9500,9600,10000,11000],
    },
    "高雄小港機場": {
        "高雄市區":[800,900,1100,1600], "屏東市區":[1100,1200,1500,2000],
        "東港":[1300,1400,1700,2200], "屏東墾丁":[2200,2300,2600,3600],
        "台南市區":[2000,2100,2400,3400], "嘉義市區":[2900,3000,3200,4200],
        "雲林":[3600,3700,3900,4900], "彰化":[4500,4600,4800,5800],
        "台中":[5000,5100,5300,6300], "苗栗":[6200,6300,6500,7500],
        "新竹":[7000,7100,7300,8300], "桃園":[8200,8300,8500,9500],
        "新北":[9200,9300,9500,10500], "台北":[9200,9300,9500,10500],
        "基隆":[10200,10300,10500,11500], "宜蘭":[11200,11300,11500,12500],
        "花蓮":[9000,9100,9300,10300], "台東":[4500,4600,4800,5800],
    },
}

# Alphard 尊爵機場接送：雲端分頁明確標示送機、接機統一價格。
ALPHARD_PRICES = {
    "桃園機場": {"宜蘭市":5000,"基隆":3500,"新北市":2300,"台北市":2300,"桃園市區":2000,"新竹市區":3500,"苗栗市":5000,"台中市":6500},
    "松山機場": {"宜蘭市":4500,"基隆":3000,"新北市":2000,"台北市":2000,"桃園市區":2300,"新竹市區":4000,"苗栗市":5500,"台中市":7000},
}

# 港口價格來源分頁目前全部標註「模擬價」，Bot 會明示參考價，避免當成正式成交價。
PORT_PRICES = {
    "嘉義布袋港": {
        "布袋／東石":[1000,1100,1300,1800], "朴子／太保":[1200,1300,1600,2100],
        "嘉義市區":[1400,1500,1800,2300], "民雄／大林":[1600,1700,2000,2500],
        "雲林斗六／虎尾":[1900,2000,2200,3200], "台南新營／鹽水":[1800,1900,2100,3100],
        "台南市區":[2400,2500,2700,3700], "彰化市區":[3000,3100,3400,4400],
        "台中市區":[3200,3300,3500,4500], "南投草屯":[3500,3600,3800,4800],
        "高雄市區":[3400,3500,3700,4700], "屏東市區":[3900,4000,4200,5200],
    },
    "東琉線（東港）": {
        "台北":[9700,9800,10000,11000], "新北":[9200,9300,9500,10500],
        "新竹":[8000,8100,8300,9200], "苗栗":[7000,7100,7300,8200],
        "台中":[5000,5100,5300,6300], "彰化":[4900,5000,5200,6200],
        "南投":[4800,4900,5100,6100], "雲林":[4200,4300,4500,5500],
        "嘉義":[3800,3900,4100,5100], "台南":[3400,3500,3700,4600],
        "高雄":[2900,3000,3200,4100], "屏東":[2700,2800,3000,3800],
    },
    "基隆港": {
        "基隆":[800,900,1200,1700], "台北":[1000,1100,1400,1900],
        "新北":[1000,1100,1400,1900], "桃園":[1400,1500,1800,2300],
        "新竹":[2100,2200,2500,3500], "苗栗":[2600,2700,3000,4000],
        "台中":[3200,3300,3500,4500], "彰化":[3800,3900,4200,5200],
        "南投":[4000,4100,4400,5400], "宜蘭":[1800,1900,2400,3400],
    },
}

VEH_IDX = {
    "五人轎車":0,"5人轎車":0,"轎車":0,"五人座":0,"5人座":0,
    "五人休旅款":1,"五人休旅":1,"5人休旅":1,"休旅":1,
    "九人座":2,"9人座":2,"8-9人座":2,"8～9人座":2,"七人座":2,"7人座":2,
    "九人座賓士":3,"VITO":3,"Vito":3,"vito":3,"賓士九人座":3,
}
ALPHARD_WORDS = ["Alphard","ALPHARD","alphard","阿法","阿爾法","埃爾法"]
TERMINAL_ALIASES = {
    "桃園機場":["桃園國際機場","桃園機場","桃機","TPE"],
    "松山機場":["台北松山機場","松山機場","松機","TSA"],
    "台中清泉崗機場":["台中國際機場","台中清泉崗機場","清泉崗機場","清泉崗","台中機場","RMQ"],
    "高雄小港機場":["高雄國際機場","高雄小港機場","小港機場","小港","KHH"],
    "嘉義布袋港":["嘉義布袋港","布袋港"],
    "東琉線（東港）":["東琉線","東港碼頭","東港港口","東港"],
    "基隆港":["基隆港","基隆郵輪港","基隆碼頭"],
}

AREA_RULES = {
    "桃園機場": [
        ("花蓮山區",["太魯閣","壽豐","瑞穗","玉里"]),("花蓮市區",["花蓮市"]),("蘇澳",["蘇澳"]),
        ("宜蘭市以南",["羅東","冬山","五結","三星","南澳"]),("宜蘭市以北",["宜蘭市","礁溪","頭城","壯圍"]),
        ("金山萬里",["金山","萬里"]),("三芝",["三芝"]),("淡水",["淡水"]),
        ("新竹香山竹東",["香山","竹東"]),("苗栗銅鑼",["銅鑼"]),("台中霧峰",["霧峰"]),("台中烏日",["烏日"]),
        ("彰化埔鹽以南",["埔鹽","溪湖","田中","北斗","田尾","二林","員林"]),
        ("彰化埔鹽以北",["彰化市","花壇","和美","鹿港","伸港"]),
        ("草屯",["草屯"]),("埔里",["埔里"]),("日月潭",["日月潭"]),("清境",["清境"]),("墾丁",["墾丁","恆春"]),
        ("台東",["台東"]),("屏東",["屏東"]),("高雄",["高雄"]),("台南",["台南"]),("嘉義",["嘉義"]),("雲林",["雲林"]),
        ("苗栗",["苗栗","竹南","頭份"]),("新竹市區",["新竹"]),("台中",["台中"]),("基隆",["基隆"]),
        ("新北市",["新北"]),("台北市",["台北"]),("桃園市區以內",["中壢","平鎮","八德","桃園市"]),
    ],
    "松山機場": [
        ("花蓮山區",["太魯閣","壽豐","瑞穗","玉里"]),("花蓮市區",["花蓮市"]),("蘇澳",["蘇澳"]),
        ("宜蘭市以南",["羅東","冬山","五結","三星","南澳"]),("宜蘭市以北",["宜蘭市","礁溪","頭城","壯圍"]),
        ("金山萬里",["金山","萬里"]),("三芝",["三芝"]),("淡水",["淡水"]),
        ("新竹香山竹東",["香山","竹東"]),("苗栗銅鑼",["銅鑼"]),("台中霧峰",["霧峰"]),("台中烏日",["烏日"]),
        ("彰化埔鹽以南",["埔鹽","溪湖","田中","北斗","田尾","二林","員林"]),
        ("彰化埔鹽以北",["彰化市","花壇","和美","鹿港","伸港"]),
        ("草屯",["草屯"]),("埔里",["埔里"]),("日月潭",["日月潭"]),("清境",["清境"]),("墾丁",["墾丁","恆春"]),
        ("台東",["台東"]),("屏東",["屏東"]),("台南",["台南"]),("嘉義",["嘉義"]),("雲林",["雲林"]),
        ("苗栗",["苗栗","竹南","頭份"]),("新竹市區",["新竹"]),("台中",["台中"]),("基隆",["基隆"]),
        ("新北市",["新北"]),("台北市",["台北"]),("桃園市區以內",["中壢","平鎮","八德","桃園市"]),
    ],
    "台中清泉崗機場": [
        ("恆春／墾丁",["墾丁","恆春"]),("南投市／草屯",["南投市","草屯"]),("台中市區",["台中市"]),
        ("彰化市區",["彰化市","花壇","和美","鹿港","伸港","員林","田尾","北斗"]),
        ("宜蘭",["宜蘭","羅東","礁溪","蘇澳"]),("基隆",["基隆"]),("台北",["台北"]),("新北",["新北"]),
        ("桃園",["桃園","中壢","平鎮","八德"]),("新竹",["新竹","竹東"]),("苗栗",["苗栗","竹南","頭份"]),
        ("集集",["集集"]),("埔里",["埔里"]),("雲林",["雲林"]),("嘉義",["嘉義"]),("台南",["台南"]),
        ("高雄",["高雄"]),("屏東",["屏東"]),("花蓮",["花蓮"]),("台東",["台東"]),
    ],
    "高雄小港機場": [
        ("屏東墾丁",["墾丁","恆春"]),("東港",["東港"]),("高雄市區",["高雄市"]),("屏東市區",["屏東市"]),
        ("台南市區",["台南市"]),("嘉義市區",["嘉義市"]),("雲林",["雲林"]),("彰化",["彰化"]),
        ("台中",["台中"]),("苗栗",["苗栗"]),("新竹",["新竹"]),("桃園",["桃園"]),("新北",["新北"]),
        ("台北",["台北"]),("基隆",["基隆"]),("宜蘭",["宜蘭"]),("花蓮",["花蓮"]),("台東",["台東"]),
    ],
    "嘉義布袋港": [
        ("布袋／東石",["布袋","東石"]),("朴子／太保",["朴子","太保"]),("民雄／大林",["民雄","大林"]),
        ("雲林斗六／虎尾",["斗六","虎尾"]),("台南新營／鹽水",["新營","鹽水"]),("嘉義市區",["嘉義市"]),
        ("台南市區",["台南市"]),("彰化市區",["彰化市","彰化"]),("台中市區",["台中市","台中"]),
        ("南投草屯",["草屯","南投"]),("高雄市區",["高雄市","高雄"]),("屏東市區",["屏東市","屏東"]),
    ],
    "東琉線（東港）": [
        ("台北",["台北"]),("新北",["新北"]),("新竹",["新竹"]),("苗栗",["苗栗"]),("台中",["台中"]),
        ("彰化",["彰化"]),("南投",["南投"]),("雲林",["雲林"]),("嘉義",["嘉義"]),("台南",["台南"]),
        ("高雄",["高雄"]),("屏東",["屏東"]),
    ],
    "基隆港": [
        ("基隆",["基隆"]),("台北",["台北"]),("新北",["新北"]),("桃園",["桃園"]),("新竹",["新竹"]),
        ("苗栗",["苗栗"]),("台中",["台中"]),("彰化",["彰化"]),("南投",["南投"]),("宜蘭",["宜蘭"]),
    ],
}

ALPHARD_AREA_RULES = {
    "桃園機場":[("宜蘭市",["宜蘭"]),("基隆",["基隆"]),("新北市",["新北"]),("台北市",["台北"]),("桃園市區",["桃園","中壢","平鎮","八德"]),("新竹市區",["新竹"]),("苗栗市",["苗栗"]),("台中市",["台中"])],
    "松山機場":[("宜蘭市",["宜蘭"]),("基隆",["基隆"]),("新北市",["新北"]),("台北市",["台北"]),("桃園市區",["桃園","中壢","平鎮","八德"]),("新竹市區",["新竹"]),("苗栗市",["苗栗"]),("台中市",["台中"])],
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
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def detect_vehicle(text: str):
    if any(k.lower() in text.lower() for k in ALPHARD_WORDS):
        return "Alphard", None, True, True
    for k, v in VEH_IDX.items():
        if k.lower() in text.lower():
            return ["五人轎車", "五人休旅款", "九人座", "九人座賓士"][v], v, True, False
    return "九人座", 2, False, False


def detect_people(text: str):
    for p in [r"(?:乘客|人數|共)\s*[:：]?\s*(\d+)\s*人", r"(?<!\d)(\d+)\s*人(?!座)"]:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def detect_luggage(text: str):
    m = re.search(r"(?:行李|大行李|件數)\s*[:：]?\s*(\d+)\s*(?:件|個)?", text)
    return int(m.group(1)) if m else None


def detect_terminal(text: str):
    for terminal, aliases in TERMINAL_ALIASES.items():
        for a in aliases:
            if a.lower() in text.lower():
                if terminal == "東琉線（東港）" and a == "東港" and not any(k in text for k in ["船", "港", "小琉球", "東琉"]):
                    continue
                return terminal
    # 客人常只寫「到桃園」，但同時附送／接機或航班。
    if "桃園" in text and any(k in text for k in ["送機", "接機", "航班", "出國", "落地", "機場接送"]):
        return "桃園機場"
    # 送船語意下可把布袋／基隆視為港口目的地。
    if any(k in text for k in ["送船", "接船", "船班"]):
        if "布袋" in text:
            return "嘉義布袋港"
        if "基隆" in text:
            return "基隆港"
    return None


def terminal_kind(terminal: str):
    return "port" if terminal in PORT_PRICES else "airport"


def _text_without_terminal(text: str, terminal: str):
    t = text
    for a in TERMINAL_ALIASES.get(terminal, []):
        t = re.sub(re.escape(a), " ", t, flags=re.I)
    return t


def detect_area_for_terminal(text: str, terminal: str, alphard=False):
    work = _text_without_terminal(text, terminal)
    rules = ALPHARD_AREA_RULES.get(terminal, []) if alphard else AREA_RULES.get(terminal, [])
    candidates = []
    for area, kws in rules:
        for kw in kws:
            pos = work.find(kw)
            if pos >= 0:
                candidates.append((len(kw), -pos, area))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][2]
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
        rf"{re.escape(label)}[\s：:]*[^0-9\n]{{0,16}}(\d{{1,2}})[/-](\d{{1,2}})[^\d]{{0,16}}(\d{{1,2}})[:：](\d{{2}})",
        text, re.I,
    )
    if m:
        return make_dt(*map(int, m.groups()))
    m = re.search(
        rf"{re.escape(label)}[\s\S]{{0,50}}?(\d{{1,2}})[/-](\d{{1,2}})[\s\S]{{0,12}}?(\d{{1,2}})[:：](\d{{2}})",
        text, re.I,
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
    return m.group(1).replace(" ", "").upper() if m else None


def holiday_info(dt):
    if not dt:
        return False, None
    tw = holidays.Taiwan(years=[dt.year])
    return (dt.date() in tw, str(tw.get(dt.date())))


def _looks_like_address(line: str):
    if not line or len(line) < 5:
        return False
    if re.search(r"航班|報價|價格|車資|時間|起飛|抵達|人數|行李|九人座|七人座|五人座|接船|送船", line):
        return False
    return bool(ADDRESS_HINT.search(line) and (re.search(r"\d", line) or "機場" in line or "港" in line or "高鐵站" in line))


def extract_addresses(text: str):
    raw_lines = [x.strip(" •-🔸📍①②③④⑤⑥⑦⑧⑨") for x in text.splitlines() if x.strip()]
    out = []
    for i, line in enumerate(raw_lines):
        if _looks_like_address(line):
            candidate = line
            if i + 1 < len(raw_lines):
                nxt = raw_lines[i + 1].strip()
                if (len(nxt) <= 12 and re.search(r"號$", nxt) and not re.search(r"縣|市|區|鄉|鎮|村|里|路|街|巷", nxt) and not candidate.endswith("號")):
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


def service_flags(text: str):
    send_words = ["送機航班", "送機時間", "送機", "送船", "送船時間", "送港", "出發到桃園"]
    pick_words = ["接機航班", "接機時間", "接機", "接船", "接船時間", "接港", "落地"]
    return any(k in text for k in send_words), any(k in text for k in pick_words)


def add_surcharges(base: int, dt, pickup: bool, terminal: str, vehicle_idx, people, text, alphard=False):
    total = base
    extras = []
    pending = []
    kind = terminal_kind(terminal)

    # 接機／接船 = 送機／送船 +200；Alphard 分頁另明訂接送同價。
    if pickup and not alphard:
        total += 200
        extras.append(("接機" if kind == "airport" else "接船", 200))

    # 夜間與六日加成：雲端規則指定四個一般機場價目表。
    if kind == "airport" and not alphard and dt:
        if 0 <= dt.hour < 6:
            total += 200
            extras.append(("夜間", 200))
        if dt.weekday() >= 5:
            total += 200
            extras.append(("六日", 200))

    if dt:
        h, name = holiday_info(dt)
        if h:
            pending.append(f"國定假日 {name}：依實際車況議價")

    if vehicle_idx in {2, 3} and people is not None and people >= 8:
        total += 100
        extras.append(("九人座第8人", 100))

    # 雲端只寫「九人座行李 +200」，未定義一般件數門檻；只有明確寫超件／行李加價才自動套。
    if vehicle_idx in {2, 3} and any(k in text for k in ["行李超件", "行李加價"]):
        total += 200
        extras.append(("九人座行李", 200))

    if any(k in text for k in ["偏遠", "山區", "特殊路段"]):
        pending.append("偏遠／山區／特殊路段：需依實際路段另行加價")
    if terminal == "台中清泉崗機場" and any(k in text for k in ["北港", "水林", "口湖", "布袋", "東石", "偏遠"]):
        pending.append("清泉崗附加區域：約 +100～500，需依實際地址確認")
    if terminal == "高雄小港機場" and "過夜" in text:
        pending.append("高雄小港過夜行程：另洽")
    return total, extras, pending


def missing_info_reply(missing, parsed=None):
    lines = ["⚠️ 資料還不夠，我先不亂報價。"]
    if parsed:
        lines += ["", "目前已辨識：", *parsed]
    lines += ["", "請補：" + "、".join(missing), "", "可直接回：", "報價", "日期時間：", "起點：", "終點（機場／港口）：", "接機/送機/接船/送船：", "車型或人數/行李："]
    return "\n".join(lines)


def ambiguity_warnings(send_service_dt, send_flight_dt):
    warnings = []
    if send_service_dt and send_flight_dt:
        diff_hours = (send_flight_dt - send_service_dt).total_seconds() / 3600
        if diff_hours > 12 or diff_hours < 0:
            warnings.append("⚠️ 送機上車時間與航班時間相差超過12小時；報價仍以『送機時間／上車時間』為主，請人工確認日期是否正確。")
    return warnings


def route_direction(area: str, terminal: str, pickup: bool):
    return f"{terminal} → {area}" if pickup else f"{area} → {terminal}"


def base_price_for(terminal: str, area: str, vehicle_idx, alphard: bool):
    if alphard:
        return ALPHARD_PRICES.get(terminal, {}).get(area)
    table = PORT_PRICES.get(terminal) if terminal_kind(terminal) == "port" else AIRPORT_PRICES.get(terminal)
    if not table or area not in table:
        return None
    return table[area][vehicle_idx]


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


async def google_route(addresses):
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not MAPS_ENABLED or not key or len(addresses) < 2:
        return None
    inter = [{"address": a} for a in addresses[1:-1]]
    body = {"origin":{"address":addresses[0]}, "destination":{"address":addresses[-1]}, "travelMode":"DRIVE", "routingPreference":"TRAFFIC_AWARE", "intermediates":inter, "optimizeWaypointOrder":bool(inter), "languageCode":"zh-TW", "units":"METRIC"}
    headers = {"Content-Type":"application/json", "X-Goog-Api-Key":key, "X-Goog-FieldMask":"routes.distanceMeters,routes.duration,routes.optimizedIntermediateWaypointIndex"}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://routes.googleapis.com/directions/v2:computeRoutes", headers=headers, json=body)
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
            "群組訊息只要包含『報價』兩個字才會觸發。\n"
            "已寫入：桃園機場、松山機場、台中清泉崗機場、高雄小港機場、嘉義布袋港、東琉線（東港）、基隆港，以及 Alphard 桃園／松山機場價目。\n"
            "可直接貼客人原文；資料不足時我才會請你補。"
        )

    terminal = detect_terminal(text)
    has_send, has_pick = service_flags(text)
    roundtrip = has_send and has_pick

    if not terminal:
        return missing_info_reply(["目的機場／港口"])

    vehicle, vehicle_idx, vehicle_explicit, alphard = detect_vehicle(text)
    if alphard and terminal not in ALPHARD_PRICES:
        return "⚠️ Alphard 正式價目目前只建有桃園機場、松山機場；其他機場／港口請人工報價。"

    area = detect_area_for_terminal(text, terminal, alphard=alphard)
    people = detect_people(text)
    luggage = detect_luggage(text)
    addresses = extract_addresses(text)
    local_addresses = [a for a in addresses if "機場" not in a and "港" not in a]
    declared = declared_point_count(text)
    multipoint_count = max(len(local_addresses), declared or 0, 1)

    parsed = [f"🎯 目的：{terminal}"]
    if area:
        parsed.append(f"📍 地區：{area}")
    if roundtrip:
        parsed.append("🔁 行程：來回")
    elif has_pick:
        parsed.append("↩️ 行程：接")
    elif has_send:
        parsed.append("➡️ 行程：送")
    if multipoint_count >= 2:
        parsed.append(f"📌 多點：{multipoint_count}點")
    if people is not None:
        parsed.append(f"👤 人數：{people}")
    if luggage is not None:
        parsed.append(f"🧳 行李：{luggage}")

    if not area:
        return missing_info_reply(["出發／目的地區或完整地址"], parsed)
    if not has_send and not has_pick:
        return missing_info_reply(["接機/送機/接船/送船"], parsed)

    base = base_price_for(terminal, area, vehicle_idx, alphard)
    if base is None:
        return f"⚠️ 目前『{terminal}／{area}／{vehicle}』沒有可直接套用的雲端價目，請人工報價。"

    kind = terminal_kind(terminal)
    send_labels = ["送機時間", "送船時間", "送機上車時間", "送船上車時間", "上車時間", "出發時間"]
    pick_labels = ["接機時間", "接船時間", "接機上車時間", "接船上車時間"]
    lines = ["🤖 小天智慧報價", f"🚐 {vehicle}", f"🎯 {terminal}"]

    if not vehicle_explicit:
        if people is None:
            lines.append("ℹ️ 未提供車型/人數，先以九人座試算")
        elif people >= 5:
            lines.append("ℹ️ 依人數先以九人座試算")
        else:
            lines.append("ℹ️ 未提供車型，暫以九人座試算")
    if multipoint_count >= 2:
        lines.append(f"📌 已辨識 {multipoint_count} 個接送點")

    if roundtrip:
        send_service_dt = extract_labeled_datetime(text, send_labels)
        send_flight_dt = extract_labeled_datetime(text, ["送機航班"])
        pickup_service_dt = extract_labeled_datetime(text, pick_labels)
        pickup_flight_dt = extract_labeled_datetime(text, ["接機航班"])

        # 送機／送船：一律以送機時間／送船時間／上車時間為主，航班時間只作備援。
        send_dt = send_service_dt or send_flight_dt
        # 接機：有指定接機時間優先；未指定才用航班抵達時間。
        pickup_dt = pickup_service_dt or pickup_flight_dt

        missing = []
        if not send_dt:
            missing.append("送機／送船日期時間")
        if not pickup_dt:
            missing.append("接機／接船日期時間")
        if missing:
            return missing_info_reply(missing, parsed)

        send_flight = extract_flight(text, "送機航班")
        pickup_flight = extract_flight(text, "接機航班")
        out_total, out_extras, out_pending = add_surcharges(base, send_dt, False, terminal, vehicle_idx, people, text, alphard)
        back_total, back_extras, back_pending = add_surcharges(base, pickup_dt, True, terminal, vehicle_idx, people, text, alphard)
        grand = out_total + back_total

        lines.append(f"📍 {area} ⇄ {terminal}")
        lines.append("")
        lines += money_lines("【送機】" if kind == "airport" else "【送船】", base, out_total, out_extras, out_pending, dt=send_dt, flight=send_flight, multipoint_count=multipoint_count)
        lines.append("")
        lines += money_lines("【接機】" if kind == "airport" else "【接船】", base, back_total, back_extras, back_pending, dt=pickup_dt, flight=pickup_flight, multipoint_count=multipoint_count)
        lines.append("")
        suffix = "＋多點加價待確認" if multipoint_count >= 2 else ""
        lines.append(f"💰 來回目前試算：${grand:,}{suffix}")
        if kind == "port":
            lines.append("⚠️ 港口價目在雲端目前標記為『模擬價』，此金額為參考客報，正式成交前請人工確認。")
        if kind == "airport":
            warnings = ambiguity_warnings(send_service_dt, send_flight_dt)
            if warnings:
                lines += ["", *warnings]
        return "\n".join(lines)

    dt_labels = pick_labels if has_pick else send_labels
    dt = extract_labeled_datetime(text, dt_labels)
    if not dt and kind == "airport":
        dt = extract_labeled_datetime(text, ["接機航班"] if has_pick else ["送機航班"])
    if not dt:
        dt = parse_any_datetime(text)
    if not dt:
        return missing_info_reply(["日期/時間"], parsed)

    pickup = has_pick and not has_send
    total, extras, pending = add_surcharges(base, dt, pickup, terminal, vehicle_idx, people, text, alphard)
    lines.append(f"📍 {route_direction(area, terminal, pickup)}")
    lines.append(f"📅 {dt.strftime('%Y/%m/%d %H:%M')}")
    lines.append(f"基本車資：${base:,}")
    for name, val in extras:
        lines.append(f"{name}：+${val:,}")
    if multipoint_count >= 2:
        lines.append(f"多點接送：{multipoint_count}點（加價待確認）")
    for note in pending:
        lines.append(note)
    suffix = "＋多點加價待確認" if multipoint_count >= 2 else ""
    lines.append(f"💰 目前試算：${total:,}{suffix}")
    if kind == "port":
        lines.append("⚠️ 港口價目在雲端目前標記為『模擬價』，正式成交前請人工確認。")
    return "\n".join(lines)


@app.get("/")
@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "xiaotian-quote-bot",
        "maps": False,
        "group_trigger": "contains:報價",
        "parser": "smart-v3-airport-port-full",
        "airports": ["桃園機場", "松山機場", "台中清泉崗機場", "高雄小港機場"],
        "ports": ["嘉義布袋港", "東琉線（東港）", "基隆港"],
        "alphard": ["桃園機場", "松山機場"],
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
