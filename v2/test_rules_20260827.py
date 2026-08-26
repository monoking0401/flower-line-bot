from flower_engine_pt_south import calculate


def test_pt_0819_real_dispatch_is_8_points_13_pieces_and_middle_base():
    text = """#1612新店北新路二段2小植光
#1507竹北集貨站1🔺瑜萱
#1507竹北集貨站1🔺柔纕
#1415竹北光明六路東二段1/Yawen葉
#1415竹北光明六路東二段1芝涵
#1808新竹東區民權路1韋全
#1415新竹北區金雅路1雅芸
#TJ/#1507新竹東區北大路1+🔺特快
#TJ忠孝+收2+1*超件/花市中轉-新竹東區北大路
#台中香緣花卉+收1盆/花市中轉-苗栗頭份中央路🔺限12前
"""

    result = calculate(text, "PT")

    assert result["total_points"] == 8
    assert result["total_pieces"] == 13
    assert result["total_buckets"] == 0
    # Fixed calculable part only; official 08/19 daily statement adds
    # special-duty allowance 465, producing 3000.
    assert result["total"] == 2535

    base = [x for x in result["lines"] if "打底" in x["name"]]
    assert len(base) == 1
    assert base[0]["amount"] == 500
    assert "中部" in base[0]["name"]


def test_limit_12_before_is_not_piece_count():
    text = "#台中香緣花卉+收1盆/花市中轉-苗栗頭份中央路🔺限12前"
    result = calculate(text, "PT")

    assert result["total_points"] == 1
    assert result["total_pieces"] == 1
    assert result["stops"][0]["pieces"] == 1


def test_pickup_two_plus_one_extra_means_three_pieces():
    text = "#TJ忠孝+收2+1*超件/花市中轉-新竹東區北大路"
    result = calculate(text, "PT")

    assert result["total_points"] == 1
    assert result["total_pieces"] == 3


def test_same_street_different_recipients_are_not_blindly_merged():
    text = """#1415竹北光明六路東二段1/Yawen葉
#1415竹北光明六路東二段1芝涵
"""
    result = calculate(text, "PT")

    assert result["total_points"] == 2
    assert result["total_pieces"] == 2


def test_transfer_addon_merges_into_single_matching_destination():
    text = """#TJ/#1507新竹東區北大路1+🔺特快
#TJ忠孝+收2+1*超件/花市中轉-新竹東區北大路
"""
    result = calculate(text, "PT")

    assert result["total_points"] == 1
    assert result["total_pieces"] == 4


def test_fulltime_same_trip_gets_each_delivery_region_base_once():
    text = """#1415桃園中壢元化路1宛婷
#1415新竹東區民權路1韋全
#1415台中西屯福科路1依伶
"""
    result = calculate(text, "正職")

    bases = [x for x in result["lines"] if "打底" in x["name"]]
    assert [x["amount"] for x in bases] == [100, 300, 500]
    assert result["total"] == 1500


def test_pt_same_trip_uses_only_southernmost_delivery_region():
    text = """#1415桃園中壢元化路1宛婷
#1415新竹東區民權路1韋全
#1415台中西屯福科路1依伶
"""
    result = calculate(text, "PT")

    bases = [x for x in result["lines"] if "打底" in x["name"]]
    assert len(bases) == 1
    assert bases[0]["amount"] == 500
    assert result["total"] == 1100


def test_collection_only_does_not_trigger_base_for_either_mode():
    text = """#1415竹北集貨站1甲
#1415台中集貨站2乙
#1507彰化集貨站1丙
"""

    for mode in ("PT", "正職"):
        result = calculate(text, mode)
        assert not [x for x in result["lines"] if "打底" in x["name"]]
        assert result["total"] == 700
