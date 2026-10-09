from v2 import main_v2 as _v2
from v2.flower_engine_dispatch_guard import calculate, format_result

_v2.calculate = calculate
_v2.format_result = format_result
import os

if os.getenv("FLOWER_DISPATCH_RELAY_ENABLED") == "true":
    from dispatch_relay import app
else:
    app = _v2.app
