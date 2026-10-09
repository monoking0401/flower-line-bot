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

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="小天報單機器人")
GROUP = re.compile(r"C[0-9a-f]{32}\Z")
USER = re.compile(r"U[0-9a-f]{32}\Z")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
COMMAND = re.compile(r"#小天綁定 [0-9a-f]{24}\Z")
DOWNSTREAM = "https://tendispatchai.onrender.com"


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
            if (isinstance(messages, list) and 1 <= len(messages) <= 2 and
                    all(exact(m, ["type", "text"]) and m["type"] == "text" and valid_text(m["text"]) for m in messages) and
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
    return {"ok": True, "service": "xiaotian-dispatch-bot", "mode": "dispatch-relay", "version": "1.0.1", "native_contact_card": False}


@app.post("/relay/info")
async def info(req: Request):
    body = await authenticated(req)
    if body != {}:
        raise HTTPException(400, "Invalid request")
    bot = await line_request("GET", "/v2/bot/info")
    endpoint = await line_request("GET", "/v2/bot/channel/webhook/endpoint")
    if bot.status_code != 200 or endpoint.status_code != 200:
        raise HTTPException(502, "LINE configuration could not be verified")
    try:
        b, w = bot.json(), endpoint.json()
        if not USER.fullmatch(b.get("userId", "")):
            raise ValueError()
        return {"bot_id": b["userId"], "display_name": b.get("displayName"), "basic_id": b.get("basicId"),
                "webhook_endpoint": w.get("endpoint"), "webhook_active": w.get("active"), "native_contact_card": False}
    except (ValueError, TypeError):
        raise HTTPException(502, "Invalid LINE configuration response")


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
        print("[DISPATCH BIND]", response.status_code, flush=True)
    except Exception:
        # A pending binding can be repeated; there is no automatic sending queue.
        print("[DISPATCH BIND] response not confirmed", flush=True)


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
    for event in body["events"]:
        if not isinstance(event, dict):
            continue
        message, source = event.get("message"), event.get("source")
        if (event.get("type") == "message" and event.get("mode") == "active" and isinstance(message, dict) and
                message.get("type") == "text" and isinstance(message.get("text"), str) and COMMAND.fullmatch(message["text"]) and
                isinstance(source, dict) and source.get("type") == "group" and isinstance(source.get("groupId"), str) and
                GROUP.fullmatch(source["groupId"]) and isinstance(event.get("timestamp"), int) and not isinstance(event["timestamp"], bool)):
            selected.append({"type": "message", "mode": "active", "timestamp": event["timestamp"],
                "source": {"type": "group", "groupId": source["groupId"]}, "message": {"type": "text", "text": message["text"]}})
    if selected:
        background.add_task(forward_binding, {"destination": bot, "events": selected})
    return {"ok": True}
