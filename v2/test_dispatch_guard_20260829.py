from flower_engine_dispatch_guard import calculate, _is_standalone_address


RAW_0827 = """#1712台中集貨站1🔺台中吳

台中市南屯區大墩十一街846號
#1511台中集貨站1🔺絜婷

台中市南屯區大墩十一街846號
#1415台中集貨站1🔺絜婷
#1415台中集貨站1🔺惠晴
#1415台中集貨站1🔺紫容
#1415台中集貨站3🔺曼郁

台中市南屯區大墩十一街846號
#1415台南*南集貨站1🔺季芳

台南市東區崇學路271-10號
#1415台南*南集貨站1🔺可依

台南市東區崇學路271-10號
#1421台南*南集貨站1🔺翔宇🔺站主請送入店內

台南市東區崇學路271-10號
————————————————
1100南轉南配🔺劉育成03
#1415高雄北集貨站2🔺深綠楠梓
#1501高雄左營南屏路1+🔺特快
#3304高雄左營大中一路1盆
————————————————
⭕台南集貨站對接
#2107台南中西區忠義路一段1玉雲
#范以函/彩心花藝/台南南區國民路1落地
#1507台南下營茅港尾1顏文君"""


def test_hyphenated_address_is_never_quantity():
    assert _is_standalone_address("台南市東區崇學路271-10號")


def test_0827_real_dispatch_matches_official_settlement():
    result = calculate(RAW_0827, "PT")

    assert result["total_points"] == 5
    assert result["total_pieces"] == 14
    assert result["transfer_pieces"] == 4
    assert result["transfer_amount"] == 200
    assert result["special_duty_amount"] == 1100
    assert result["total"] == 4000

    priced = {line["name"]: line["amount"] for line in result["lines"]}
    assert priced["花市南"] == 1900
    assert priced["PT推定終點打底（台南）"] == 800
    assert priced["南轉南"] == 200
    assert priced["特別勤務加給"] == 1100


def test_settlement_guard_still_wins_over_dispatch_guard():
    text = """08/24 新竹日配打底+300
08/24 花市南2點21件1桶 400+1950
小計：2650
總計：2650"""
    result = calculate(text, "PT")
    assert result["kind"] == "settlement"
    assert result["detail_total"] == 2650
    assert result["total"] == 2650
