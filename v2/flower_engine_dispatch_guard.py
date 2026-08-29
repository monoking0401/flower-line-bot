import re

try:
    from . import flower_engine_production as production
except ImportError:
    import flower_engine_production as production


TRANSFER_FEE_PER_PIECE = 50
TRANSFER_START_RE = re.compile(r"^\s*(\d{2,4})\s*南轉南配")
SEPARATOR_RE = re.compile(r"^[-—─_= ]{3,}$")
STANDALONE_ADDRESS_RE = re.compile(
    r"(?:路|街|巷|弄).*[0-9]+(?:\s*-\s*[0-9]+)?\s*號(?:\s*\d+\s*樓(?:之\d+)?)?\s*$"
)

# 08/27 formal case: repeated 台南*南集貨站 entries are the same physical
# collection point.  Register the alias so the legacy regrouping layer merges
# them as one point instead of three incomplete street/name rows.
FIXED_STATION_ALIASES = {
    "台南*南集貨站": (
        "台南市東區崇學路271-10號",
        "台南",
        True,
    ),
    "台南南集貨站": (
        "台南市東區崇學路271-10號",
        "台南",
        True,
    ),
}


def _install_fixed_station_aliases():
    production.legacy.FIXED.update(FIXED_STATION_ALIASES)


def _is_standalone_address(line):
    """True for address-only helper lines that must never become quantities.

    Example: 台南市東區崇學路271-10號.  The old implicit quantity parser
    skipped the trailing 10 because it was followed by 號, but incorrectly
    treated 271 (before the hyphen) as 271 pieces.
    """
    if not line or "#" in line:
        return False
    if re.search(r"\d+\s*(?:件|盆|桶)", line):
        return False
    return bool(STANDALONE_ADDRESS_RE.search(line))


def _is_control_line(line):
    if not line:
        return False
    if "對接" in line and ("⭕" in line or "集貨站" in line):
        return True
    return bool(
        re.match(
            r"^(?:司機資料|駕駛[:：]|電話[:：]|車牌[:：]|車型[:：]|顏色[:：])",
            line,
        )
    )


def _split_dispatch(text):
    """Separate standard delivery rows from an explicit 南轉南 section."""
    main_lines = []
    transfer_lines = []
    in_transfer = False
    special_amount = 0

    for raw in text.splitlines():
        line = raw.strip()

        start = TRANSFER_START_RE.match(line)
        if start:
            # Formal 08/27 settlement confirms the leading 1100 on
            # "1100南轉南配" is the explicit special-duty allowance.
            special_amount = int(start.group(1))
            in_transfer = True
            continue

        if in_transfer:
            if SEPARATOR_RE.fullmatch(line):
                in_transfer = False
                continue
            if _is_control_line(line):
                in_transfer = False
                continue
            if _is_standalone_address(line):
                continue
            if line:
                transfer_lines.append(raw)
            continue

        if SEPARATOR_RE.fullmatch(line):
            continue
        if _is_control_line(line):
            continue
        if _is_standalone_address(line):
            continue

        main_lines.append(raw)

    return "\n".join(main_lines), "\n".join(transfer_lines), special_amount


def _count_transfer_pieces(text):
    if not text.strip():
        return 0

    prepared = production.legacy._preprocess(text)
    items, _stops, _endpoints = production.legacy._parse_dispatch(prepared)
    return sum(item.get("pieces", 0) for item in items)


def calculate(text, mode):
    if mode not in {"PT", "正職"}:
        raise ValueError("mode must be PT or 正職")

    # Preserve the dedicated day-end settlement verifier added in the previous
    # production fix.  Settlement text should never pass through dispatch
    # sanitizing or implicit quantity parsing.
    if production._looks_like_settlement(text):
        return production.calculate(text, mode)

    _install_fixed_station_aliases()
    main_text, transfer_text, special_amount = _split_dispatch(text)

    result = production.calculate(main_text, mode)

    transfer_pieces = _count_transfer_pieces(transfer_text)
    if transfer_pieces:
        transfer_amount = transfer_pieces * TRANSFER_FEE_PER_PIECE
        result["lines"].append({
            "name": "南轉南",
            "amount": transfer_amount,
            "desc": f"{transfer_pieces}件×{TRANSFER_FEE_PER_PIECE}",
        })
        result["total"] += transfer_amount
        result["transfer_pieces"] = transfer_pieces
        result["transfer_amount"] = transfer_amount

    if special_amount:
        result["lines"].append({
            "name": "特別勤務加給",
            "amount": special_amount,
            "desc": "南轉南配行首明寫金額",
        })
        result["total"] += special_amount
        result["special_duty_amount"] = special_amount

    return result


def format_result(result):
    return production.format_result(result)
