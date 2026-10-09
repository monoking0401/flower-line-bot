import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
import dispatch_relay as relay

KEY="independent-test-bridge-key-"*3
BOT="U"+"2"*32
GROUP="C"+"1"*32
RETRY="12345678-1234-4234-8234-123456789012"

@pytest.fixture
def client(monkeypatch):
    for k,v in {"LINE_RELAY_BRIDGE_KEY":KEY,"LINE_RELAY_BOT_ID":BOT,"LINE_CHANNEL_ACCESS_TOKEN":"test-token","LINE_CHANNEL_SECRET":"test-channel-secret"}.items():
        monkeypatch.setenv(k,v)
    return TestClient(relay.app)

def signed(path,body):
    raw=json.dumps(body,ensure_ascii=False,separators=(",",":")).encode()
    t=str(int(time.time()))
    return raw,{"Content-Type":"application/json","X-Relay-Timestamp":t,"X-Relay-Signature":relay.signature(KEY,t,"POST",path,raw)}

def line_body():
    return {"path":"/v2/bot/message/push","method":"POST","body":{"to":GROUP,"messages":[{"type":"text","text":" 原文\r\n🚗 "}]},"retry_key":RETRY}

def webhook(events):
    return {"destination":BOT,"events":events}

def event(text="#小天綁定 "+"a"*24):
    return {"type":"message","mode":"active","timestamp":int(time.time()*1000),"replyToken":"never-forward","source":{"type":"group","groupId":GROUP,"userId":BOT},"message":{"type":"text","text":text,"id":"private-id"}}

def line_signed(body):
    raw=json.dumps(body,ensure_ascii=False).encode()
    sig=base64.b64encode(hmac.new(b"test-channel-secret",raw,hashlib.sha256).digest()).decode()
    return raw,{"Content-Type":"application/json","X-Line-Signature":sig}

def test_push_preserves_complete_text_and_retry_key(client,monkeypatch):
    mock=AsyncMock(return_value=httpx.Response(200,json={"sentMessages":[{"quoteToken":"private"}]}))
    monkeypatch.setattr(relay,"line_request",mock)
    b=line_body();raw,h=signed("/relay/line",b)
    r=client.post("/relay/line",content=raw,headers=h)
    assert r.status_code==200 and r.json()=={}
    mock.assert_awaited_once_with("POST",b["path"],b["body"],RETRY)

@pytest.mark.parametrize("patch",[{"path":"https://evil.example"},{"path":"/v2/bot/message/reply"},{"method":"DELETE"},{"retry_key":None},{"body":{"to":BOT,"messages":[{"type":"text","text":"x"}]}},{"body":{"to":GROUP,"messages":[{"type":"contact","text":"fake-card"}]}}])
def test_restricted_transport_cannot_send_to_users_or_arbitrary_apis(client,monkeypatch,patch):
    mock=AsyncMock();monkeypatch.setattr(relay,"line_request",mock)
    raw,h=signed("/relay/line",{**line_body(),**patch})
    assert client.post("/relay/line",content=raw,headers=h).status_code==400
    mock.assert_not_awaited()

def test_bad_signature_body_timestamp_and_path_are_rejected_before_line_call(client,monkeypatch):
    mock=AsyncMock();monkeypatch.setattr(relay,"line_request",mock)
    raw,h=signed("/relay/line",line_body())
    for path,data,headers in [("/relay/line",raw,{**h,"X-Relay-Signature":"0"*64}),("/relay/line",raw+b" ",h),("/relay/line",raw,{**h,"X-Relay-Timestamp":"0000000000"}),("/relay/line?extra=1",raw,h)]:
        assert client.post(path,content=data,headers=headers).status_code==401
    mock.assert_not_awaited()

@pytest.mark.parametrize("value",["", "中"*5001, "🚗"*2501, "x\u0000", "\ud800"])
def test_invalid_or_overlong_text_is_not_truncated(value):
    assert not relay.valid_text(value)

def test_utf16_limit_and_separate_ordered_messages_are_preserved(client,monkeypatch):
    assert relay.valid_text("🚗"*2500)
    mock=AsyncMock(return_value=httpx.Response(200,json={}))
    monkeypatch.setattr(relay,"line_request",mock)
    b=line_body();b["body"]["messages"].insert(0,{"type":"text","text":"資訊"})
    raw,h=signed("/relay/line",b)
    assert client.post("/relay/line",content=raw,headers=h).status_code==200
    assert mock.await_args.args[2]["messages"]==b["body"]["messages"]

def test_409_acceptance_header_is_preserved_without_private_line_body(client,monkeypatch):
    mock=AsyncMock(return_value=httpx.Response(409,json={"secret":"private"},headers={"X-Line-Accepted-Request-Id":"accepted"}))
    monkeypatch.setattr(relay,"line_request",mock)
    raw,h=signed("/relay/line",line_body());r=client.post("/relay/line",content=raw,headers=h)
    assert r.status_code==409 and r.headers["x-line-accepted-request-id"]=="accepted" and r.json()=={}

def test_group_summary_omits_member_photo_and_other_private_fields(client,monkeypatch):
    monkeypatch.setattr(relay,"line_request",AsyncMock(return_value=httpx.Response(200,json={"groupId":GROUP,"groupName":"目標群組","pictureUrl":"private-photo"})))
    raw,h=signed("/relay/line",{"path":f"/v2/bot/group/{GROUP}/summary","method":"GET","body":None,"retry_key":None})
    r=client.post("/relay/line",content=raw,headers=h)
    assert r.json()=={"groupId":GROUP,"groupName":"目標群組"}

def test_verified_webhook_only_forwards_binding_without_sender_replytoken_or_normal_chat(client,monkeypatch):
    mock=AsyncMock();monkeypatch.setattr(relay,"forward_binding",mock)
    raw,h=line_signed(webhook([event(),event("PT"),event("上車台中 車資9275"),{**event(),"mode":"standby"}]))
    assert client.post("/webhook",content=raw,headers=h).status_code==200
    mock.assert_awaited_once()
    sent=mock.await_args.args[0]
    assert len(sent["events"])==1 and sent["destination"]==BOT
    assert sent["events"][0]["source"]=={"type":"group","groupId":GROUP}
    assert "replyToken" not in json.dumps(sent) and "userId" not in json.dumps(sent)

def test_wrong_line_signature_and_different_bot_cannot_forward(client,monkeypatch):
    mock=AsyncMock();monkeypatch.setattr(relay,"forward_binding",mock)
    raw,h=line_signed(webhook([event()]))
    assert client.post("/webhook",content=raw+b" ",headers=h).status_code==401
    raw,h=line_signed({"destination":"U"+"3"*32,"events":[event()]})
    assert client.post("/webhook",content=raw,headers=h).status_code==400
    mock.assert_not_awaited()

def test_info_uses_existing_token_server_side_and_confirms_real_bot_and_endpoint(client,monkeypatch):
    mock=AsyncMock(side_effect=[httpx.Response(200,json={"userId":BOT,"displayName":"花市專用","basicId":"@017pcooo"}),httpx.Response(200,json={"endpoint":"https://flower-line-bot.onrender.com/webhook","active":True})])
    monkeypatch.setattr(relay,"line_request",mock)
    raw,h=signed("/relay/info",{});r=client.post("/relay/info",content=raw,headers=h)
    assert r.status_code==200 and r.json()["basic_id"]=="@017pcooo" and r.json()["webhook_active"] is True
    assert "test-token" not in r.text and r.json()["native_contact_card"] is False

def test_default_main_retains_old_flower_and_quote_files(client,monkeypatch):
    import importlib,main
    monkeypatch.delenv("FLOWER_DISPATCH_RELAY_ENABLED",raising=False)
    importlib.reload(main)
    from v2 import main_v2
    assert main.app is main_v2.app
    monkeypatch.setenv("FLOWER_DISPATCH_RELAY_ENABLED","true")
    importlib.reload(main)
    assert main.app is relay.app
