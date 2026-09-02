"""Runtime patch layer for the Xiaotian quote service only.

This package hook keeps the original flower bot untouched while allowing
small quote-rule corrections without rewriting quote/main.py wholesale.
"""

import importlib.abc
import importlib.machinery
import sys


def _apply_quote_patch(module):
    if getattr(module, "_QUOTE_RULE_PATCHED", False):
        return

    original_surcharges = module.add_surcharges
    original_area = module.detect_area_for_terminal

    def detect_area_for_terminal(text, terminal, alphard=False):
        area = original_area(text, terminal, alphard=alphard)
        if area:
            return area

        # 客人常省略「台中市」只寫行政區＋路名。
        # 已確認案例：大雅區屬台中清泉崗機場價目中的「台中市區」。
        if terminal == "台中清泉崗機場" and not alphard:
            work = module._text_without_terminal(text, terminal)
            if "大雅區" in work or "大雅" in work:
                return "台中市區"

        return None

    def missing_info_reply(missing, parsed=None):
        # 分成兩個 LINE 訊息：第一則說明，第二則只有可直接複製填寫的格式。
        return [
            "📋 資訊不完整，請複製下一則格式填寫後再傳送：",
            (
                "日期：\n"
                "時間：\n"
                "出發地：\n"
                "目的地：\n"
                "人數：\n"
                "行李：\n"
                "行程：送機／接機／送船／接船\n"
                "（擇一）\n\n"
                "★報價★"
            ),
        ]

    async def line_reply(token, text):
        """LINE reply supports one text or multiple text bubbles in one reply token."""
        access = module.os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
        if not access:
            raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN missing")

        if isinstance(text, (list, tuple)):
            texts = [str(item) for item in text if str(item).strip()][:5]
        else:
            texts = [str(text)]
        messages = [{"type": "text", "text": item[:4900]} for item in texts]

        async with module.httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
                json={"replyToken": token, "messages": messages},
            )
            print("[LINE]", r.status_code, r.text, flush=True)
            r.raise_for_status()

    def add_surcharges(base, dt, pickup, terminal, vehicle_idx, people, text, alphard=False):
        total, extras, pending = original_surcharges(
            base, dt, pickup, terminal, vehicle_idx, people, text, alphard
        )

        # 基隆港原始價目圖明列：夜間 00:00-06:00 +200、六日 +200。
        if terminal == "基隆港" and not alphard and dt:
            names = {name for name, _ in extras}
            if 0 <= dt.hour < 6 and "夜間" not in names:
                total += 200
                extras.append(("夜間", 200))
            if dt.weekday() >= 5 and "六日" not in names:
                total += 200
                extras.append(("六日", 200))

        # 基隆港原始價目圖另明列「行李 +200」。目前依九人座／九人座賓士
        # 且訊息有明確行李件數時套用，避免未提供行李資訊時自行猜測。
        luggage = module.detect_luggage(text)
        if (
            terminal == "基隆港"
            and vehicle_idx in {2, 3}
            and luggage is not None
            and luggage > 0
            and not any(name == "九人座行李" for name, _ in extras)
        ):
            total += 200
            extras.append(("九人座行李", 200))

        return total, extras, pending

    module.detect_area_for_terminal = detect_area_for_terminal
    module.missing_info_reply = missing_info_reply
    module.line_reply = line_reply
    module.add_surcharges = add_surcharges
    module._QUOTE_RULE_PATCHED = True


class _QuoteMainLoader(importlib.abc.Loader):
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def create_module(self, spec):
        create = getattr(self.wrapped, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        _apply_quote_patch(module)


class _QuoteMainFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != "quote.main":
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader and not isinstance(spec.loader, _QuoteMainLoader):
            spec.loader = _QuoteMainLoader(spec.loader)
        return spec


if "quote.main" in sys.modules:
    _apply_quote_patch(sys.modules["quote.main"])
else:
    sys.meta_path.insert(0, _QuoteMainFinder())
