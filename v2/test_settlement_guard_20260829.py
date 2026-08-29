from flower_engine_production import calculate, format_result


FULLTIME_BAD_SETTLEMENT = """林岳賢 日結

808
1388976089176
————————————————
08/24 實習收貨助理×1
時段 400
08/24 桃園日配打底
+100
08/24 新竹日配打底
+300
08/24 中部日配打底
+500
08/24 花市雙北1點1件
135
08/24 花市南10點12件
2000+400
08/24 樓層費1 100

08/25 新竹日配打底
+300
08/25 中部日配打底
+500
08/25 花市雙北1點1件
135
08/25 花市南9點10件
1800+200
08/25 樓層費1 100
08/25 #日光花藝+收2盆/民生東路五段-延平南路+中山堂+上樓 400
08/25 空運代墊170元
$3435+170
————————————————
小計：8070
代收：0
代墊：170
總計：8240元
驗算
"""


PT_GOOD_SETTLEMENT = """劉仲偉 日結

08/24 新竹日配打底+300
08/24 花市南2點21件1桶 400+1950

08/25 桃園日配打底+100
08/25 花市雙北4點4件 540
08/25 花市南4點4件 800
08/25 特別勤務加給 65

08/26 新竹日配打底+300
08/26 花市南6點15件1桶 1200+950
08/26 樓層費1 100

08/27 台南日配打底+800
08/27 花市南5點14件 1000+900
08/27 南轉南4件 200
08/27 特別勤務加給 1100

小計：10705
代收：0
總計：10705元
"""


def test_settlement_money_is_never_parsed_as_delivery_quantity():
    result = calculate(FULLTIME_BAD_SETTLEMENT, "正職")
    assert result["kind"] == "settlement"
    assert result["total_pieces"] == 24
    assert result["total_pieces"] < 100
    assert dict(result["daily"]) == {"08/24": 3935, "08/25": 3435}
    assert result["detail_subtotal"] == 7370
    assert result["advance"] == 170
    assert result["detail_total"] == 7540


def test_settlement_checks_flower_formula_and_declared_totals():
    result = calculate(FULLTIME_BAD_SETTLEMENT, "正職")
    assert result["formula_total"] == 7240
    assert [(x["expected"], x["written"]) for x in result["corrections"]] == [
        (2200, 2400),
        (1900, 2000),
    ]
    output = format_result(result)
    assert "依原文明細應付：7,540元" in output
    assert "依公式校正後應付：7,240元" in output
    assert "原文總計寫 8,240 元" in output
    assert "70,800" not in output


def test_known_pt_settlement_still_verifies_exactly():
    result = calculate(PT_GOOD_SETTLEMENT, "PT")
    assert result["kind"] == "settlement"
    assert dict(result["daily"]) == {
        "08/24": 2650,
        "08/25": 1505,
        "08/26": 2550,
        "08/27": 4000,
    }
    assert result["detail_total"] == 10705
    assert result["formula_total"] == 10705
    assert result["corrections"] == []
    assert result["warnings"] == []
    assert result["price_status"] == "日結驗算一致"
