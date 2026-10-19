"""Dedicated Xiaotian dispatch LINE channel; credentials never leave this service.

Only verified binding commands are forwarded to the member backend. Ordinary group
chat is ignored. All push requests originate from the authenticated member backend.
The old flower implementation is retired. Independent quotation code is separate.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import httpx
from dispatch_formats import dispatch_format_reply
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="小天報單專用機")
GROUP = re.compile(r"C[0-9a-f]{32}\Z")
USER = re.compile(r"U[0-9a-f]{32}\Z")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
COMMAND = re.compile(r"#小天綁定 [0-9a-f]{24}\Z")
DOWNSTREAM = "https://tendispatchai.onrender.com"
TEMPLATES = json.loads(Path(__file__).with_name("trip-templates.json").read_text(encoding="utf-8"))
DOCUMENT_COMMAND = re.compile(r"^(?:#製單綁定 |製單(?:\n|$)|修改\n|製單說明$|司機清單$|選司機 |儲存司機$|承租人同乘客$|租賃單$|公司清單$|選公司 |行程(?: |$)|選行程 |查單$|選單 |預覽$|正式輸出$|發送$|確認發送$|發送狀態$|取消$)|^(?=.*(?:行事曆|派車單)).{1,200}$")


def template_reply(value):
    if not isinstance(value, str):
        return None
    dispatch = dispatch_format_reply(value)
    if dispatch:
        return dispatch
    command = value.strip().rstrip("。！!：:")
    aliases = {"送機表單": "送機格式", "接機表單": "接機格式", "接駁表單": "接駁格式"}
    command = aliases.get(command, command)
    if command in ("用車格式", "填寫格式"):
        return "送機格式\n接機格式\n接駁格式"
    return TEMPLATES.get(command)


def document_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return False
    u = urlparse(value)
    return (u.scheme == "https" and u.netloc == "tendispatchai.onrender.com" and
            u.path == "/v1/documents/download" and not u.fragment and
            set(parse_qs(u.query)) == {"t"} and len(parse_qs(u.query)["t"]) == 1)


def document_messages(messages):
    if not isinstance(messages, list) or len(messages) != 2:
        return False
    image, pdf = messages
    return (exact(image, ["type", "originalContentUrl", "previewImageUrl"]) and image["type"] == "image" and
            document_url(image["previewImageUrl"]) and document_url(image["originalContentUrl"]) and
            exact(pdf, ["type", "text"]) and pdf["type"] == "text" and
            isinstance(pdf["text"], str) and pdf["text"].startswith("派車單PDF：") and document_url(pdf["text"][7:]))


def secret():
    key = os.getenv("LINE_RELAY_BRIDGE_KEY", "")
    if len(key) < 32 or not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
        raise HTTPException(503, "Relay not configured")
    return key


def signature(key, timestamp, method, path, raw):
    prefix = f"TenDispatchAI-bridge-v1\n{timestamp}\n{method}\n{path}\n".encode()
    return hmac.new(key.encode(), prefix + raw, hashlib.sha256).hexdigest()


async def bounded_body(req):
    if req.headers.get("content-type", "").split(";")[0].lower().strip() != "application/json":
        raise HTTPException(415, "JSON required")
    if req.headers.get("content-encoding", "identity") != "identity":
        raise HTTPException(415, "Encoding not supported")
    raw = b""
    async for chunk in req.stream():
        raw += chunk
        if len(raw) > 65536:
            raise HTTPException(413, "Body too large")
    return raw


async def authenticated(req):
    key = secret()
    raw = await bounded_body(req)
    stamp = req.headers.get("x-relay-timestamp", "")
    if not re.fullmatch(r"[0-9]{10}", stamp) or abs(time.time() - int(stamp)) > 60:
        raise HTTPException(401, "Invalid authentication")
    expected = signature(key, stamp, req.method, req.url.path, raw)
    supplied=req.headers.get("x-relay-signature", "")
    if req.url.query or not re.fullmatch(r"[0-9a-f]{64}",supplied) or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Invalid authentication")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Invalid JSON")
    return body


def exact(value, keys):
    return isinstance(value, dict) and set(value) == set(keys)


def valid_text(value):
    if not isinstance(value, str) or not value.strip() or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        return False
    try:
        return len(value.encode("utf-16-le")) // 2 <= 5000
    except UnicodeError:
        return False


def validate_line(body):
    if not exact(body, ["path", "method", "body", "retry_key"]):
        raise HTTPException(400, "Invalid request")
    if not isinstance(body["path"], str):
        raise HTTPException(400, "Invalid path")
    if re.fullmatch(r"/v2/bot/group/C[0-9a-f]{32}/summary", body["path"]) and body["method"] == "GET":
        if body["body"] is None and body["retry_key"] is None:
            return
    elif body["path"] == "/v2/bot/message/push" and body["method"] == "POST":
        data = body["body"]
        if exact(data, ["to", "messages"]) and isinstance(data["to"], str) and GROUP.fullmatch(data["to"]):
            messages = data["messages"]
            if ((isinstance(messages, list) and 1 <= len(messages) <= 2 and
                    all(exact(m, ["type", "text"]) and m["type"] == "text" and valid_text(m["text"]) for m in messages) or document_messages(messages)) and
                    isinstance(body["retry_key"], str) and UUID.fullmatch(body["retry_key"])):
                return
    raise HTTPException(400, "Unsupported operation")


async def line_request(method, path, body=None, retry_key=None):
    headers = {"Authorization": "Bearer " + os.environ["LINE_CHANNEL_ACCESS_TOKEN"]}
    if retry_key:
        headers["X-Line-Retry-Key"] = retry_key
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            return await client.request(method, "https://api.line.me" + path, headers=headers, json=body)
    except httpx.HTTPError:
        raise HTTPException(504, "LINE response unknown")


@app.get("/")
@app.get("/health")
async def health():
    return {"ok": True, "service": "xiaotian-dispatch-bot", "mode": "dispatch-relay", "version": "1.2.1", "native_contact_card": False, "trip_templates": True, "driver_dispatch_templates": True, "command_menu": True}


@app.post("/relay/info")
async def info(req: Request):
    body = await authenticated(req)
    if body != {} and not (exact(body, ["verify_webhook"]) and body["verify_webhook"] is True):
        raise HTTPException(400, "Invalid request")
    bot = await line_request("GET", "/v2/bot/info")
    endpoint = await line_request("GET", "/v2/bot/channel/webhook/endpoint")
    if bot.status_code != 200 or endpoint.status_code != 200:
        raise HTTPException(502, "LINE configuration could not be verified")
    try:
        b, w = bot.json(), endpoint.json()
        if not USER.fullmatch(b.get("userId", "")):
            raise ValueError()
        result = {"bot_id": b["userId"], "display_name": b.get("displayName"), "basic_id": b.get("basicId"),
                "webhook_endpoint": w.get("endpoint"), "webhook_active": w.get("active"), "native_contact_card": False}
    except (ValueError, TypeError):
        raise HTTPException(502, "Invalid LINE configuration response")
    if body:
        # Official communication check only: no custom endpoint or group message.
        check = await line_request("POST", "/v2/bot/channel/webhook/test", {})
        if check.status_code != 200:
            raise HTTPException(502, "LINE webhook check unavailable")
        try:
            checked = check.json()
            if type(checked.get("success")) is not bool or type(checked.get("statusCode")) is not int:
                raise ValueError()
            result["webhook_test"] = {"success": checked["success"], "status_code": checked["statusCode"]}
        except (ValueError, TypeError):
            raise HTTPException(502, "Invalid LINE webhook check")
    return result


@app.post("/relay/line")
async def proxy_line(req: Request):
    body = await authenticated(req)
    validate_line(body)
    response = await line_request(body["method"], body["path"], body["body"], body["retry_key"])
    if body["method"] == "POST":
        headers = {}
        accepted = response.headers.get("x-line-accepted-request-id", "")
        if accepted:
            headers["X-Line-Accepted-Request-Id"] = accepted
        # Discard quote tokens, sent message IDs and private error bodies.
        return Response(content="{}", media_type="application/json", status_code=response.status_code, headers=headers)
    if response.status_code != 200:
        return JSONResponse({"error": "LINE rejected request"}, status_code=response.status_code)
    try:
        result = response.json()
        gid = body["path"].split("/")[4]
        if result.get("groupId") != gid or not valid_text(result.get("groupName")) or len(result["groupName"]) > 100:
            raise ValueError()
        return {"groupId": result["groupId"], "groupName": result["groupName"]}
    except (ValueError, TypeError):
        raise HTTPException(502, "Invalid LINE group response")


async def forward_binding(body):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    stamp = str(int(time.time()))
    path = "/v1/relay/bridge-webhook"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            response = await client.post(DOWNSTREAM + path, content=raw, headers={"Content-Type": "application/json",
                "X-Relay-Timestamp": stamp, "X-Relay-Signature": signature(secret(), stamp, "POST", path, raw)})
        summary = {"event": "dispatch_binding_forward", "status": response.status_code}
        if response.status_code == 200:
            try:
                counters = response.json().get("binding_counts", {})
                for name in ("bound", "name_mismatch", "code_not_found", "ignored"):
                    if type(counters.get(name)) is int and 0 <= counters[name] <= 100:
                        summary[name] = counters[name]
            except (ValueError, TypeError, AttributeError):
                pass
        print(json.dumps(summary), flush=True)
    except Exception:
        # A pending binding can be repeated; there is no automatic sending queue.
        print("[DISPATCH BIND] response not confirmed", flush=True)


async def reply_text(reply_token, value):
    if not isinstance(reply_token, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,256}", reply_token):
        return
    if not valid_text(value):
        value = "內容過長，請縮小行程查詢範圍，或在APK開啟單據。"
    try:
        response = await line_request("POST", "/v2/bot/message/reply", {"replyToken": reply_token, "messages": [{"type": "text", "text": value}]})
        print(json.dumps({"event": "dispatch_reply_result", "status": response.status_code, "accepted": response.status_code == 200}), flush=True)
    except Exception:
        print('[DISPATCH REPLY] response not confirmed', flush=True)


async def forward_document(bot, event, reply_token):
    raw = json.dumps({"destination": bot, "event": event}, ensure_ascii=False, separators=(",", ":")).encode()
    stamp = str(int(time.time()))
    path = "/v1/documents/bridge-command"
    try:
        async with httpx.AsyncClient(timeout=50, follow_redirects=False) as client:
            response = await client.post(DOWNSTREAM + path, content=raw, headers={"Content-Type": "application/json",
                "X-Relay-Timestamp": stamp, "X-Relay-Signature": signature(secret(), stamp, "POST", path, raw)})
        result = response.json()
        value = result.get("reply") if response.status_code == 200 else result.get("error", {}).get("message", "製單服務尚未就緒，請稍後再試。")
        await reply_text(reply_token, value or "未取得完整結果，請在APK查詢目前單據。")
    except Exception:
        await reply_text(reply_token, "製單結果尚未確認，請查單；不要重貼建立另一張。")


@app.post("/webhook")
async def webhook(req: Request, background: BackgroundTasks):
    secret()
    raw = await bounded_body(req)
    expected = base64.b64encode(hmac.new(os.environ["LINE_CHANNEL_SECRET"].encode(), raw, hashlib.sha256).digest()).decode()
    supplied=req.headers.get("x-line-signature", "")
    if not re.fullmatch(r"[A-Za-z0-9+/]{43}=",supplied) or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Invalid LINE signature")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Invalid JSON")
    bot = os.getenv("LINE_RELAY_BOT_ID", "")
    if not USER.fullmatch(bot):
        raise HTTPException(503, "Bot identity not verified")
    if not isinstance(body, dict) or body.get("destination") != bot or not isinstance(body.get("events"), list) or len(body["events"]) > 100:
        raise HTTPException(400, "Invalid LINE events")
    selected = []
    template_count = 0
    max_event_age_ms = 0
    for event in body["events"]:
        if not isinstance(event, dict):
            continue
        message, source = event.get("message"), event.get("source")
        if (event.get("type") == "message" and event.get("mode") == "active" and isinstance(message, dict) and
                message.get("type") == "text" and isinstance(source, dict) and isinstance(event.get("timestamp"), int) and
                abs(time.time() * 1000 - event["timestamp"]) < 300000):
            template = template_reply(message.get("text"))
            if template:
                template_count += 1
                max_event_age_ms = max(max_event_age_ms, int(time.time() * 1000 - event["timestamp"]))
                background.add_task(reply_text, event.get("replyToken"), template)
            elif (source.get("type") == "user" and USER.fullmatch(source.get("userId", "")) and
                  isinstance(message.get("text"), str) and len(message["text"]) <= 12000 and DOCUMENT_COMMAND.search(message["text"])):
                selected_event = {"source": {"type": "user", "userId": source["userId"]},
                                  "message": {"type": "text", "text": message["text"], "id": message.get("id", "")},
                                  "webhookEventId": event.get("webhookEventId", ""), "timestamp": event["timestamp"]}
                background.add_task(forward_document, bot, selected_event, event.get("replyToken"))
        if (event.get("type") == "message" and event.get("mode") == "active" and isinstance(message, dict) and
                message.get("type") == "text" and isinstance(message.get("text"), str) and COMMAND.fullmatch(message["text"]) and
                isinstance(source, dict) and source.get("type") == "group" and isinstance(source.get("groupId"), str) and
                GROUP.fullmatch(source["groupId"]) and isinstance(event.get("timestamp"), int) and not isinstance(event["timestamp"], bool)):
            selected.append({"type": "message", "mode": "active", "timestamp": event["timestamp"],
                "source": {"type": "group", "groupId": source["groupId"]}, "message": {"type": "text", "text": message["text"]}})
    print(json.dumps({"event": "dispatch_webhook_received", "event_count": len(body["events"]),
                      "binding_count": len(selected), "template_count": template_count, "max_template_age_ms": max_event_age_ms}), flush=True)
    if selected:
        background.add_task(forward_binding, {"destination": bot, "events": selected})
    return {"ok": True}
