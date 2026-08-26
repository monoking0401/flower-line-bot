from flower_engine_v2 import (
    calculate,
    parse_dispatch,
)


def test_pt_0821():
    text = """PT
#1320中壢延平路2老k🔺急件
#1511中壢民族路1/謝淑文
#曾聰明花坊#1709楊梅自立街2🔺特快
#曾聰明花坊#1320楊梅自立街1
#1612新店北新路二段1小植光
#1415竹北集貨站1🔺雅梅
#1415竹北集貨站1🔺雨潔
#2506新竹竹北莊敬六街1/敘思
#孫明益/新竹新馥7件
#1501新竹市經國路三段1/黃老師
"""

    r = calculate(text, "PT")

    assert r["total_points"] == 8
    assert r["total_pieces"] == 18
    assert r["total"] == 2835


def test_phone_not_piece():
    text = """#1520忠孝東路四段1上慈
🔺送達電話通知 0906139759
"""

    items, stops, endpoints = parse_dispatch(text)

    assert len(stops) == 1
    assert stops[0]["pieces"] == 1


def test_zhongxiao_is_north():
    text = "#1520忠孝東路四段1上慈"

    r = calculate(text, "正職")

    assert r["total_points"] == 1
    assert r["total_pieces"] == 1
    assert r["stops"][0]["region"] == "雙北"


def test_unknown_not_general():
    text = "#9999未知神秘路1測試"

    r = calculate(text, "正職")

    assert r["stops"][0]["region"] is None
    assert r["price_status"] == "待確認"


def test_full_phone_case():
    text = """#1415竹北集貨站1🔺意玟
#1415竹北集貨站1🔺季亭
#1415竹北集貨站1🔺鈞蘋
#1613竹北集貨站1🔺心慧
#孫明益/新竹新馥17件+3桶
#1520忠孝東路四段1上慈 🔺送達電話通知 0906139759
#1715新店永業路1美淑
#1311板橋民生路二段1阿蓁
#1415林口忠孝路1靖文
#1415蘆竹機捷二路1耀儒
#1415桃園中壢元化路1宛婷
#秀媚#怡心園/桃園中壢永福路1益
#1311桃園正光路1娜家
"""

    r = calculate(text, "正職")

    assert r["total_points"] == 10
    assert r["total_pieces"] == 29
    assert r["total_buckets"] == 3
