import os
import re
import json
import hmac
import hashlib
import base64

import httpx
from fastapi import FastAPI, Request, Header, HTTPException

try:
    from .flower_engine_v2 import calculate, format_result
except ImportError:
    from flower_engine_v2 import calculate, format_result


app = FastAPI()

# V2 第一階段先沿用記憶體模式
# 後續再升級成資料庫持久化
STATE = {}


def source_id(event):
    source = event.get("source", {})

    return (
        source.get("groupId")
        or source.get("roomId")
        or source.get("userId")
        or "unknown"
    )


def valid_signature(raw, signature):
    secret = os.getenv(
        "LINE_CHANNEL_SECRET",
        ""
    )

    if not secret or not signature:
        return False

    digest = hmac.new(
        secret.encode("utf-8"),
        raw,
        hashlib.sha256
    ).digest()

    expected = base64.b64encode(
        digest
    ).decode("utf-8")

    return hmac.compare_digest(
        expected,
        signature
    )


async def reply_message(reply_token, text):
    access_token = os.getenv(
        "LINE_CHANNEL_ACCESS_TOKEN",
        ""
    )

    if not access_token:
        raise RuntimeError(
            "LINE_CHANNEL_ACCESS_TOKEN is empty"
        )

    # LINE 單則文字訊息不要過長
    text = text[:4900]

    async with httpx.AsyncClient(
        timeout=15
    ) as client:

        response = await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization":
                    f"Bearer {access_token}",
                "Content-Type":
                    "application/json",
            },
            json={
                "replyToken": reply_token,
                "messages": [
                    {
                        "type": "text",
                        "text": text,
                    }
                ],
            },
        )

        print(
            "[LINE REPLY]",
            response.status_code,
            response.text,
            flush=True
        )

        response.raise_for_status()


def looks_like_dispatch(text):
    if "#" in text:
        return True

    if re.search(
        r"\d+\s*(件|盆|桶)",
        text
    ):
        return True

    return False


@app.get("/")
@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "flower-line-bot-v2",
        "engine": "smart-v2",
    }


@app.post("/webhook")
async def webhook(
    req: Request,
    x_line_signature: str | None = Header(
        default=None
    ),
):
    raw = await req.body()

    print(
        "\n========== V2 WEBHOOK ==========",
        flush=True
    )

    if not valid_signature(
        raw,
        x_line_signature or ""
    ):
        print(
            "[V2] invalid signature",
            flush=True
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

    body = json.loads(raw)

    events = body.get(
        "events",
        []
    )

    print(
        "[V2] events =",
        len(events),
        flush=True
    )

    for event in events:

        if event.get("type") != "message":
            continue

        message = event.get(
            "message",
            {}
        )

        if message.get("type") != "text":
            continue

        text = message.get(
            "text",
            ""
        ).strip()

        reply_token = event.get(
            "replyToken"
        )

        if not reply_token:
            continue

        sid = source_id(event)

        print(
            "[V2] sid =",
            sid,
            "| text =",
            repr(text),
            flush=True
        )

        # =================================
        # 模式指令
        # 只有整則訊息完全相符才切換
        # =================================

        if text.upper() == "PT":

            STATE[sid] = "PT"

            await reply_message(
                reply_token,
                "✅ 已切換為 PT 模式。"
            )

            continue

        if text == "正職":

            STATE[sid] = "正職"

            await reply_message(
                reply_token,
                "✅ 已切換為 正職 模式。"
            )

            continue

        if text == "模式":

            mode = STATE.get(
                sid
            )

            if mode:
                msg = (
                    "目前模式："
                    f"{mode}"
                )
            else:
                msg = (
                    "目前尚未設定模式。\n"
                    "請單獨輸入：PT 或 正職"
                )

            await reply_message(
                reply_token,
                msg
            )

            continue

        if text in {
            "重設模式",
            "清除模式",
        }:

            STATE.pop(
                sid,
                None
            )

            await reply_message(
                reply_token,
                "✅ 模式已清除。\n"
                "請重新輸入 PT 或 正職。"
            )

            continue

        # =================================
        # 一般派單
        # =================================

        if not looks_like_dispatch(
            text
        ):
            print(
                "[V2] skip: not dispatch",
                flush=True
            )
            continue

        mode = STATE.get(
            sid
        )

        if not mode:

            await reply_message(
                reply_token,
                "⚠️ 尚未設定花市模式。\n"
                "請先單獨輸入：\n"
                "PT\n"
                "或\n"
                "正職"
            )

            continue

        try:

            result = calculate(
                text,
                mode
            )

            output = format_result(
                result
            )

        except Exception as exc:

            print(
                "[V2 CALC ERROR]",
                repr(exc),
                flush=True
            )

            await reply_message(
                reply_token,
                "⚠️ V2 計算時發生錯誤。\n"
                "本筆沒有自動亂算金額，"
                "請保留原始派單供檢查。"
            )

            continue

        print(
            "[V2 CALC]",
            mode,
            result.get(
                "total_points"
            ),
            "points",
            result.get(
                "total_pieces"
            ),
            "pieces",
            result.get(
                "total"
            ),
            "dollars",
            flush=True
        )

        await reply_message(
            reply_token,
            output
        )

    print(
        "========== V2 WEBHOOK DONE ==========\n",
        flush=True
    )

    return {
        "ok": True
    }
