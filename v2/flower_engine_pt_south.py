from .flower_engine_v2 import BASE, calculate as _base_calculate, format_result


SOUTH_ORDER = {
    "桃園": 1,
    "新竹": 2,
    "中部": 3,
    "雲嘉": 4,
    "台南": 5,
    "高雄": 6,
}


def _southmost_delivery_region(stops):
    regions = [
        stop["region"]
        for stop in stops
        if (
            not stop["is_collection"]
            and stop["region"] in BASE
        )
    ]

    if not regions:
        return None

    return max(
        regions,
        key=lambda name: SOUTH_ORDER[name],
    )


def calculate(text, mode):
    result = _base_calculate(text, mode)

    if mode != "PT" or result["endpoints"]:
        return result

    inferred = _southmost_delivery_region(
        result["stops"]
    )

    if not inferred:
        return result

    target_index = None

    for index, line in enumerate(result["lines"]):
        if line["name"].startswith("PT推定終點打底"):
            target_index = index
            break

    new_line = {
        "name": f"PT推定終點打底（{inferred}）",
        "amount": BASE[inferred],
        "desc": "未明寫終點，依南下宅配最南端推定",
    }

    if target_index is None:
        result["lines"].append(new_line)
        result["total"] += BASE[inferred]
    else:
        old_amount = result["lines"][target_index]["amount"]
        result["lines"][target_index] = new_line
        result["total"] += BASE[inferred] - old_amount

    result["warnings"] = [
        warning
        for warning in result["warnings"]
        if not warning.startswith("PT終點未明寫")
    ]

    result["warnings"].append(
        "PT終點未明寫，"
        f"依南下宅配最南端推定為「{inferred}」"
    )

    return result
