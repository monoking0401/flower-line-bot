"""Runtime patch layer for the Xiaotian quote service only.

This package hook keeps the original flower bot untouched while allowing
small quote-rule corrections without rewriting quote/main.py wholesale.
"""

import importlib.abc
import importlib.machinery
import sys


def _apply_quote_patch(module):
    if getattr(module, "_KEELUNG_RULE_PATCHED", False):
        return

    original = module.add_surcharges

    def add_surcharges(base, dt, pickup, terminal, vehicle_idx, people, text, alphard=False):
        total, extras, pending = original(
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

    module.add_surcharges = add_surcharges
    module._KEELUNG_RULE_PATCHED = True


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
