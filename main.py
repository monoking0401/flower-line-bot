import os,re,json,hmac,hashlib,base64
from collections import OrderedDict
import httpx
from fastapi import FastAPI,Request,Header,HTTPException

app=FastAPI()
STATE={}
BASE={"桃園":100,"新竹":300,"中部":500,"雲嘉":600,"台南":800,"高雄":1000}
REGIONS=OrderedDict([
("桃園",["桃園","中壢","楊梅","平鎮","龜山","八德","蘆竹","大溪","龍潭","大園","觀音","新屋"]),
("新竹",["新竹","竹北","湖口","新豐","竹東","芎林","關西","新埔","寶山"]),
("中部",["苗栗","頭份","竹南","台中","臺中","彰化","南投","員林","鹿港","沙鹿","大甲"]),
("雲嘉",["雲林","斗六","虎尾","嘉義","民雄","太保","朴子"]),
("台南",["台南","臺南","新營","永康","新市","善化","安定"]),
("高雄",["高雄","小港","左營","鳳山","岡山","楠梓"])])
NORTH=["台北","臺北","新北","新店","板橋","中和","永和","三重","蘆洲","新莊","土城","樹林","汐止","淡水","林口"]
FIX={
"竹北集貨站":("新竹縣竹北市縣政八街58號","新竹",True),
"台中集貨站":("台中市南屯區大墩十一街846號","中部",True),
"台灣造花":("台中市南屯區大墩十一街846號","中部",True),
"彰化集貨站":("彰化市中華西路216號","中部",True),
"新竹新馥":("新竹市東區柴橋路139巷59-25號","新竹",False),
"新馥":("新竹市東區柴橋路139巷59-25號","新竹",False)}
FLAGS=["急件","特快","特別勤務"]

def region(s):
    if any(x in s for x in NORTH): return "雙北"
    for r,ws in REGIONS.items():
        if any(x in s for x in ws): return r

def fixed(s):
    for k in sorted(FIX,key=len,reverse=True):
        if k in s: return k,*FIX[k]

def clean(s):
    for f in FLAGS:s=s.replace(f,"")
    return s.replace("🔺","").replace("▲","").strip(" /+-")

def one(tok):
    raw=tok;t=tok.lstrip("#")
    m=re.match(r"(.+?)#\d{4}(.+)$",t)
    if m:
        body=m.group(2)
    else:
        m=re.match(r"\d{4}(.+)$",t)
        body=m.group(1) if m else t

    rec0=""
    if "/" in body:
        a,b=body.split("/",1)
        if (region(b) or fixed(b)) and not any(x in a for x in "路街巷站市縣"):
            rec0=clean(a)
            body=b

    q=list(re.finditer(r"(\d+)\s*(件|盆)",body))
    buckets=0

    if q:
        m=q[-1]
        pieces=int(m.group(1))
        span=m.span()
        bm=re.search(r"(\d+)\s*桶",body)
        buckets=int(bm.group(1)) if bm else 0
    else:
        cand=list(re.finditer(r"(\d+)(?=$|(?:/|🔺|▲|[A-Za-z\u4e00-\u9fff]))",body))
        m=cand[-1] if cand else None
        if not m:return
        pieces=int(m.group(1))
        span=m.span()

    before=body[:span[0]].strip(" /+-")
    after=re.sub(r"\+?\s*\d+\s*桶","",body[span[1]:])
    rec=rec0 or clean(after)

    fx=fixed(before)
    if fx:
        loc,addr,rg,col=fx
    else:
        loc=addr=before
        rg=region(before)
        col="集貨站" in before or "集運站" in before

    return {
        "raw":raw,
        "loc":loc,
        "addr":addr,
        "rg":rg,
        "col":col,
        "cat":"雙北" if rg=="雙北" else "南",
        "pieces":pieces,
        "buckets":buckets,
        "rec":rec,
        "flags":[f for f in FLAGS if f in raw]
    }

def parse(text):
    items=[]
    for tok in re.split(r"\s+",text.strip()):
        if not tok or tok.upper() in {"PT","正職"} or tok.startswith("終點"):
            continue
        if tok.startswith("#") or re.search(r"\d+\s*(件|盆|桶)",tok):
            x=one(tok)
            if x:items.append(x)

    g=OrderedDict()
    for x in items:
        k=re.sub(r"[\s　,，/／#]","",x["addr"]).lower()
        if k not in g:
            g[k]={**x,"pieces":0,"buckets":0,"recs":[],"flags":[]}

        s=g[k]
        s["pieces"]+=x["pieces"]
        s["buckets"]+=x["buckets"]

        if x["rec"]:
            s["recs"].append(x["rec"])

        for f in x["flags"]:
            if f not in s["flags"]:
                s["flags"].append(f)

    epm=re.search(r"終點\s*[:：=]\s*(桃園|新竹|中部|雲嘉|台南|高雄|雙北)",text)
    return items,list(g.values()),epm.group(1) if epm else None

def calc(text,mode):
    items,stops,ep=parse(text)
    total=0
    lines=[]
    warn=[]

    ns=[s for s in stops if s["cat"]=="雙北"]
    ss=[s for s in stops if s["cat"]!="雙北"]

    if ns:
        p=len(ns)
        n=sum(s["pieces"] for s in ns)
        a=p*135+max(n-p,0)*100
        total+=a
        lines.append(("花市雙北",a,f"{p}點{n}件"))

    if ss:
        p=len(ss)
        n=sum(s["pieces"] for s in ss)
        b=sum(s["buckets"] for s in ss)
        a=p*200+max(n-p,0)*100+b*50
        total+=a
        lines.append(("花市南",a,f"{p}點{n}件"+(f"＋{b}桶" if b else "")))

    if mode=="PT" and any(not s["col"] for s in ss):
        if not ep:
            for x in reversed(items):
                if x["rg"] and x["rg"]!="雙北":
                    ep=x["rg"]
                    break

        if ep in BASE:
            total+=BASE[ep]
            lines.append((f"PT終點打底（{ep}）",BASE[ep],"每趟只算最終區域1次"))

            if "終點" not in text:
                warn.append(f"PT終點未明寫，依最後一筆派單推定為「{ep}」")
        else:
            warn.append("⚠️ PT無法判斷終點，請加：終點=新竹")

    if mode=="正職":
        regs=[]
        for s in ss:
            if not s["col"] and s["rg"] in BASE and s["rg"] not in regs:
                regs.append(s["rg"])

        for r in regs:
            total+=BASE[r]
            lines.append((f"正職區域打底（{r}）",BASE[r],"正職與PT分開"))

    for s in stops:
        if s["flags"]:
            warn.append(f"{s['loc']}：{'/'.join(s['flags'])}（只標記，不自動加價）")

    out=[
        f"【花市自動計算｜{mode}】",
        f"總配送：{len(stops)}點{sum(s['pieces'] for s in stops)}件",
        "",
        "配送整理："
    ]

    for i,s in enumerate(stops,1):
        rec="、".join(s["recs"]) if s["recs"] else "未標收件人"
        out.append(
            f"{i}. {s['loc']}"
            f"{'【集貨/集運】' if s['col'] else ''}"
            f"｜{s['pieces']}件｜{rec}"
        )

    out+=["","計價："]

    for a,b,c in lines:
        out.append(f"- {a}：{b}元（{c}）")

    out+=["",f"預估日結：{total:,}元"]

    if warn:
        out+=["","提醒："]+[f"- {x}" for x in warn]

    return "\n".join(out)

def source_id(e):
    s=e.get("source",{})
    return s.get("groupId") or s.get("roomId") or s.get("userId") or "unknown"

def valid(raw,sig):
    sec=os.getenv("LINE_CHANNEL_SECRET","")

    if not sec or not sig:
        return False

    d=hmac.new(sec.encode(),raw,hashlib.sha256).digest()

    return hmac.compare_digest(
        base64.b64encode(d).decode(),
        sig
    )

async def reply(token,text):
    key=os.getenv("LINE_CHANNEL_ACCESS_TOKEN","")

    async with httpx.AsyncClient(timeout=15) as c:
        r=await c.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization":f"Bearer {key}",
                "Content-Type":"application/json"
            },
            json={
                "replyToken":token,
                "messages":[
                    {"type":"text","text":text[:4900]}
                ]
            }
        )
        r.raise_for_status()

@app.get("/")
@app.get("/health")
async def health():
    return {
        "ok":True,
        "service":"flower-line-bot"
    }

@app.post("/webhook")
async def webhook(
    req:Request,
    x_line_signature:str|None=Header(default=None)
):
    raw=await req.body()

    if not valid(raw,x_line_signature or ""):
        raise HTTPException(401,"Invalid signature")

    body=json.loads(raw)

    for e in body.get("events",[]):
        if e.get("type")!="message":
            continue

        if e.get("message",{}).get("type")!="text":
            continue

        text=e["message"]["text"].strip()
        token=e.get("replyToken")
        sid=source_id(e)

        if not token:
            continue

        if text.upper()=="PT":
            STATE[sid]="PT"
            await reply(token,"✅ 已切換為 PT 模式。")
            continue

        if text=="正職":
            STATE[sid]="正職"
            await reply(token,"✅ 已切換為 正職 模式。")
            continue

        if text=="模式":
            await reply(
                token,
                f"目前模式：{STATE.get(sid,'尚未設定')}"
            )
            continue

        first=next(
            (x.strip() for x in text.splitlines() if x.strip()),
            ""
        )

        mode=(
            "PT"
            if first.upper()=="PT"
            else (
                "正職"
                if first=="正職"
                else STATE.get(sid)
            )
        )

        if first.upper()=="PT" or first=="正職":
            STATE[sid]=mode

        if not mode:
            continue

        if "#" not in text and not re.search(r"\d+\s*(件|盆)",text):
            continue

        await reply(token,calc(text,mode))

    return {"ok":True}
