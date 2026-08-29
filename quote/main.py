import os, re, json, hmac, hashlib, base64
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import holidays
from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI()
TZ = ZoneInfo("Asia/Taipei")
MAPS_ENABLED = os.getenv("ENABLE_GOOGLE_MAPS", "false").lower() in {"1", "true", "yes", "on"}

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
VEH_IDX = {"五人轎車":0, "5人轎車":0, "五人座":0, "5人座":0,
           "五人休旅":1, "5人休旅":1, "休旅":1,
           "九人座":2, "9人座":2, "8-9人座":2, "七人座":2, "7人座":2,
           "九人座賓士":3, "VITO":3, "Vito":3, "賓士九人座":3}


def valid_signature(raw: bytes, sig: str) -> bool:
    secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if not secret or not sig: return False
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), sig)

async def line_reply(token: str, text: str):
    access = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not access: raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN missing")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post("https://api.line.me/v2/bot/message/reply",
            headers={"Authorization":f"Bearer {access}","Content-Type":"application/json"},
            json={"replyToken":token,"messages":[{"type":"text","text":text[:4900]}]})
        print("[LINE]", r.status_code, r.text, flush=True)
        r.raise_for_status()


def detect_vehicle(text: str):
    for k,v in VEH_IDX.items():
        if k.lower() in text.lower(): return k,v
    return "九人座",2


def detect_area(text: str):
    rules = [
        ("墾丁", ["墾丁","恆春"]),("清境",["清境"]),("日月潭",["日月潭"]),("埔里",["埔里"]),("草屯",["草屯"]),
        ("台東",["台東"]),("花蓮山區",["太魯閣","壽豐","瑞穗","玉里"]),("花蓮市區",["花蓮"]),
        ("屏東",["屏東"]),("高雄",["高雄"]),("台南",["台南"]),("嘉義",["嘉義"]),("雲林",["雲林"]),
        ("彰化埔鹽以南",["埔鹽","溪湖","田中","北斗","田尾","二林","員林"]),
        ("彰化埔鹽以北",["彰化","花壇","和美","鹿港","伸港"]),
        ("台中霧峰",["霧峰"]),("台中烏日",["烏日"]),("台中",["台中"]),
        ("苗栗銅鑼",["銅鑼"]),("苗栗",["苗栗","竹南","頭份"]),
        ("新竹香山竹東",["香山","竹東"]),("新竹市區",["新竹"]),
        ("淡水",["淡水"]),("三芝",["三芝"]),("金山萬里",["金山","萬里"]),("基隆",["基隆"]),
        ("新北市",["新北"]),("台北市",["台北"]),("桃園市區以內",["桃園","中壢","平鎮","八德"]),
    ]
    for area, kws in rules:
        if any(k in text for k in kws): return area
    return None


def parse_datetime(text: str):
    now = datetime.now(TZ)
    m = re.search(r"(?:(\d{1,2})[/-](\d{1,2}))?.{0,12}?(\d{1,2})[:：](\d{2})", text)
    if not m: return None
    month = int(m.group(1) or now.month); day = int(m.group(2) or now.day)
    hour = int(m.group(3)); minute = int(m.group(4))
    year = now.year if (month,day) >= (now.month,now.day) else now.year+1
    try: return datetime(year,month,day,hour,minute,tzinfo=TZ)
    except ValueError: return None


def holiday_info(dt):
    if not dt: return False, None
    tw = holidays.Taiwan(years=[dt.year])
    return (dt.date() in tw, str(tw.get(dt.date())))


def extract_addresses(text):
    lines=[x.strip(" •-🔸📍①②③④⑤⑥⑦⑧⑨") for x in text.splitlines() if x.strip()]
    out=[]
    for x in lines:
        if re.search(r"(縣|市|區|鄉|鎮|路|街|巷|號|機場|高鐵站)",x) and not re.search(r"車資|航班|報價|基本車資",x):
            if x not in out: out.append(x)
    return out[:10]

async def google_route(addresses):
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not MAPS_ENABLED or not key or len(addresses)<2: return None
    inter=[{"address":a} for a in addresses[1:-1]]
    body={"origin":{"address":addresses[0]},"destination":{"address":addresses[-1]},
          "travelMode":"DRIVE","routingPreference":"TRAFFIC_AWARE",
          "intermediates":inter,"optimizeWaypointOrder":bool(inter),"languageCode":"zh-TW","units":"METRIC"}
    headers={"Content-Type":"application/json","X-Goog-Api-Key":key,
             "X-Goog-FieldMask":"routes.distanceMeters,routes.duration,routes.optimizedIntermediateWaypointIndex"}
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post("https://routes.googleapis.com/directions/v2:computeRoutes",headers=headers,json=body)
        print("[MAPS]",r.status_code,r.text[:300],flush=True)
        if r.status_code!=200: return None
        routes=r.json().get("routes",[])
        if not routes: return None
        rr=routes[0]; secs=int(str(rr.get("duration","0s")).rstrip("s") or 0)
        return {"km":round(rr.get("distanceMeters",0)/1000,1),"minutes":round(secs/60)}


def calculate_quote(text, dt):
    vehicle, idx=detect_vehicle(text)
    area=detect_area(text)
    if not any(k in text for k in ["桃機","桃園機場","桃園國際機場"]): return None
    if not area: return None
    base=TAOYUAN_PRICES[area][idx]; total=base; extras=[]
    pickup=any(k in text for k in ["接機","機場接","桃機接","落地"])
    if pickup: total+=200; extras.append(("接機等候",200))
    if dt:
        if 0<=dt.hour<6: total+=200; extras.append(("夜間",200))
        if dt.weekday()>=5: total+=200; extras.append(("六日",200))
        h,name=holiday_info(dt)
        if h: extras.append((f"國定假日 {name}","另議"))
    addrs=extract_addresses(text)
    local=[a for a in addrs if "機場" not in a]
    if len(local)>=3:
        total+=200; extras.append(("多點接送",200))
    return {"vehicle":vehicle,"area":area,"base":base,"total":total,"extras":extras,"addresses":addrs}

async def build_reply(text):
    if text.strip() in {"幫助","說明","help","HELP","報價幫助"}:
        return "🤖 小天AI報價\n群組訊息只要包含『報價』兩個字才會觸發。\n例：請幫我報價 12/7 00:30 埔里→桃園機場 九人座 送機"
    dt=parse_datetime(text); q=calculate_quote(text,dt)
    if not q:
        return "⚠️ 試算版目前先支援桃園機場正式價目。\n請輸入日期時間、地區/完整地址、車型、接機或送機。"
    route=await google_route(q["addresses"])
    lines=["🤖 小天AI報價",f"🚐 {q['vehicle']}",f"📍 {q['area']} ⇄ 桃園機場"]
    if dt: lines.append(f"📅 {dt.strftime('%Y/%m/%d %H:%M')}")
    if route: lines.extend([f"🛣 約 {route['km']} km",f"⏱ 約 {route['minutes']} 分鐘"])
    lines.append(f"基本車資：${q['base']:,}")
    for name,val in q["extras"]:
        lines.append(f"{name}：+${val:,}" if isinstance(val,int) else f"{name}：{val}")
    lines.append(f"💰 建議客報：${q['total']:,}")
    return "\n".join(lines)

@app.get("/")
@app.get("/health")
async def health():
    return {"ok":True,"service":"xiaotian-quote-bot","maps":MAPS_ENABLED and bool(os.getenv("GOOGLE_MAPS_API_KEY"))}

@app.post("/webhook")
async def webhook(req:Request,x_line_signature:str|None=Header(default=None)):
    raw=await req.body()
    if not valid_signature(raw,x_line_signature or ""):
        raise HTTPException(401,"Invalid signature")
    body=json.loads(raw)
    for ev in body.get("events",[]):
        if ev.get("type")!="message" or ev.get("message",{}).get("type")!="text": continue
        text=ev["message"].get("text","").strip(); source=ev.get("source",{}).get("type")
        if source in {"group","room"} and "報價" not in text: continue
        if "報價" in text: text=text.replace("報價","",1).strip()
        token=ev.get("replyToken")
        if token:
            try: await line_reply(token,await build_reply(text))
            except Exception as exc: print("[ERR]",repr(exc),flush=True)
    return {"ok":True}
