from flower_engine_production import calculate


def _floor_lines(result):
    return [line for line in result["lines"] if line["name"] == "樓層費"]


def test_xinzhu_xinbei_road_is_xinzhu_not_twin_cities():
    result = calculate("#1607新竹東區新北路1盆", "PT")
    assert result["total_points"] == 1
    assert result["total_pieces"] == 1
    assert result["stops"][0]["region"] == "新竹"
    assert result["total"] == 500


def test_floor_service_aliases_each_add_100_once():
    for marker in ("送上樓", "上樓", "樓層費", "樓層", "樓層/"):
        result = calculate(f"#1607{marker}新竹東區新北路1盆", "PT")
        assert result["total_points"] == 1, marker
        assert result["total_pieces"] == 1, marker
        assert result["stops"][0]["region"] == "新竹", marker
        assert result["total"] == 600, marker
        assert len(_floor_lines(result)) == 1, marker
        assert _floor_lines(result)[0]["amount"] == 100, marker


def test_multiple_floor_service_words_same_trip_still_only_add_100():
    result = calculate(
        "#1607送上樓/樓層費/新竹東區新北路1盆",
        "PT",
    )
    assert result["total"] == 600
    assert len(_floor_lines(result)) == 1


def test_plain_numeric_floor_5f_and_8f_do_not_trigger_fee_or_piece_error():
    cases = (
        "#1607新竹東區新北路99號5樓1王小明",
        "#1607新竹東區新北路99號8F1王小明",
    )
    for text in cases:
        result = calculate(text, "PT")
        assert result["total_points"] == 1, text
        assert result["total_pieces"] == 1, text
        assert result["stops"][0]["region"] == "新竹", text
        assert result["total"] == 500, text
        assert not _floor_lines(result), text


def test_floor_fee_applies_in_both_pt_and_fulltime_modes():
    text = "#1607上樓新竹東區新北路1盆"
    for mode in ("PT", "正職"):
        result = calculate(text, mode)
        assert result["total"] == 600, mode
        assert len(_floor_lines(result)) == 1, mode


def test_real_0826_dispatch_with_floor_note_is_2550():
    text = """#1415竹北集貨站1🔺意玟🔺站主請送店內
#1805竹北集貨站1🔺意玟🔺站主請送店內
#1108竹北集貨站1🔺春玥
#3807竹北光明一路1盆
#1808新竹東區民權路1韋全
#孫明益/新竹新馥8件+1桶
#1311新竹經國路二段1蓁禛
#1607送上樓/新竹東區新北路1盆"""
    result = calculate(text, "PT")
    assert result["total_points"] == 6
    assert result["total_pieces"] == 15
    assert result["total_buckets"] == 1
    assert all(stop["region"] == "新竹" for stop in result["stops"])
    assert result["total"] == 2550
    assert len(_floor_lines(result)) == 1


def test_real_0826_dispatch_without_floor_note_is_2450():
    text = """#1415竹北集貨站1🔺意玟🔺站主請送店內
#1805竹北集貨站1🔺意玟🔺站主請送店內
#1108竹北集貨站1🔺春玥
#3807竹北光明一路1盆
#1808新竹東區民權路1韋全
#孫明益/新竹新馥8件+1桶
#1311新竹經國路二段1蓁禛
#1607新竹東區新北路1盆"""
    result = calculate(text, "PT")
    assert result["total_points"] == 6
    assert result["total_pieces"] == 15
    assert result["total_buckets"] == 1
    assert result["total"] == 2450
    assert not _floor_lines(result)
