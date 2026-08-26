from flower_engine_pt_south import calculate


def test_pt_uses_southernmost_delivery_region_not_text_order():
    text = """#1415竹北集貨站1 意玟
#1415竹北集貨站1 季亭
#1415竹北集貨站1 鈞蘋
#1613竹北集貨站1 心慧
#孫明益/新竹新馥17件+3桶
#1520忠孝東路四段1 上慈
#1715新店永業路1 美淑
#1311板橋民生路二段1 阿蓁
#1415林口忠孝路1 靖文
#1415蘆竹機捷二路1 耀儒
#1415桃園中壢元化路1 宛婷
#秀媚#怡心園/桃園中壢永福路1盆
#1311桃園正光路1 娜家"""

    result = calculate(text, "PT")

    assert result["total_points"] == 10
    assert result["total_pieces"] == 29
    assert result["total_buckets"] == 3
    assert result["total"] == 4090

    pt_lines = [
        line
        for line in result["lines"]
        if line["name"].startswith("PT推定終點打底")
    ]

    assert len(pt_lines) == 1
    assert pt_lines[0]["name"] == "PT推定終點打底（新竹）"
    assert pt_lines[0]["amount"] == 300


def test_pt_collection_station_does_not_define_endpoint():
    text = """#1311桃園正光路1 娜家
#1415台中集貨站1 集貨"""

    result = calculate(text, "PT")

    pt_lines = [
        line
        for line in result["lines"]
        if line["name"].startswith("PT推定終點打底")
    ]

    assert len(pt_lines) == 1
    assert pt_lines[0]["name"] == "PT推定終點打底（桃園）"
    assert pt_lines[0]["amount"] == 100
