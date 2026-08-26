from flower_engine_v3 import calculate, parse_dispatch


def test_pt_0806_matches_boss_day_end():
    text = """#1415竹北集貨站1🔺瑜萱
#1415竹北集貨站1🔺鈞蘋
#1415竹北集貨站1🔺靜雯
#1415竹北集貨站1🔺曼庭
#1415竹北集貨站1🔺靖澐
#1415竹北集貨站1🔺宛諭
#1415竹北集貨站1🔺沛宸
#1415竹北集貨站1🔺品毅
#1507竹北集貨站1🔺季亭
#1501竹北集貨站1🔺絲涵
#1613新竹東區建新路1溫室有花🔺FCT站
#孫明益/新竹新馥11件+2桶"""
    result = calculate(text, "PT")
    assert result["total_points"] == 3
    assert result["total_pieces"] == 22
    assert result["total_buckets"] == 2
    assert result["total"] == 2900


def test_pt_0807_matches_boss_day_end():
    text = """#1114竹北集貨站1🔺意玟🔺站主送店內
#1415竹北集貨站1🔺如慧
#1108竹北集貨站1🔺春玥
#孫明益/新竹新馥10件+1桶
#1415台中集貨站1🔺其恩
#1415台中集貨站1🔺妘芸
#1712台中集貨站2🔺台中吳
#1613台中集貨站1🔺心嫻
#1415台中西屯市政北一路1如妙🔺中午前
#1311台中西屯杏林路1銖禾禾"""
    result = calculate(text, "PT")
    assert result["total_points"] == 5
    assert result["total_pieces"] == 20
    assert result["total_buckets"] == 1
    assert result["total"] == 3050


def test_pt_0813_matches_boss_day_end():
    text = """#1114竹北集貨站1🔺意玟🔺站主請送入店內
#1712台中集貨站2🔺台中吳
#1415台中集貨站1🔺侑靜
#1415台中集貨站3🔺紹成
#1415台中集貨站4🔺曼郁
#1415台中集貨站1🔺依琹
#1711台中集貨站1🔺林其
#2107台中南屯大墩六街1穎宣
#1415台中烏日高鐵東一路3冠瑩
#Tiffeny/#1421台中中清路二段1
#1501台中北屯崇德路三段1詠潔"""
    result = calculate(text, "PT")
    assert result["total_points"] == 6
    assert result["total_pieces"] == 19
    assert result["total"] == 3000


def test_pt_0818_pure_collection_has_no_base():
    text = """#1415竹北集貨站1🔺劉品毅
#1415竹北集貨站1🔺翊勤
#1415竹北集貨站1🔺怡瑾
#1415竹北集貨站1🔺静雯
#1415竹北集貨站1🔺珈飴
#1108竹北集貨站1🔺春玥
#1114竹北集貨站1🔺意玟🔺站主請送店內
#1805竹北集貨站1🔺意玟🔺站主請送店內
#1507竹北集貨站1🔺日日好
#1501竹北集貨站1🔺絲涵
#1415台中集貨站1🔺彥均
#1415台中集貨站1🔺蕙宇
#1415台中集貨站1🔺明恩
#1711台中集貨站1🔺林其
#1108台中集貨站1🔺凱葳
#1114台中集貨站2🔺宇璇
#1507彰化集貨站1🔺亮彤"""
    result = calculate(text, "PT")
    assert result["total_points"] == 3
    assert result["total_pieces"] == 18
    assert result["total"] == 2100
    assert not any("打底" in line["name"] for line in result["lines"])


def test_pt_0819_transfer_and_limit_time_are_parsed_correctly():
    text = """#1612新店北新路二段2小植光
#1507竹北集貨站1🔺瑜萱
#1507竹北集貨站1🔺柔纕
#1415竹北光明六路東二段1/Yawen葉
#1415竹北光明六路東二段1芝涵
#1808新竹東區民權路1韋全
#1415新竹北區金雅路1雅芸
#TJ/#1507新竹東區北大路1+🔺特快
#TJ忠孝+收2+1*超件/花市中轉-新竹東區北大路
#台中香緣花卉+收1盆/花市中轉-苗栗頭份中央路🔺限12前"""
    result = calculate(text, "PT")
    assert result["total_points"] == 8
    assert result["total_pieces"] == 13
    assert result["total_buckets"] == 0
    assert result["total"] == 2535
    assert any(
        line["name"] == "花市雙北" and line["amount"] == 235
        for line in result["lines"]
    )
    assert any(
        line["name"] == "花市南" and line["amount"] == 1800
        for line in result["lines"]
    )
    assert any(
        line["name"] == "PT推定終點打底（中部）"
        and line["amount"] == 500
        for line in result["lines"]
    )


def test_pt_0819_known_special_add_matches_formal_salary():
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
特別勤務=465"""
    result = calculate(text, "PT")
    assert result["total"] == 3000


def test_pt_0821_matches_boss_day_end():
    text = """#1320中壢延平路2老k🔺急件
#1511中壢民族路1/謝淑文
#曾聰明花坊#1709楊梅自立街2🔺特快
#曾聰明花坊#1320楊梅自立街1
#1612新店北新路二段1小植光
#1415竹北集貨站1🔺雅梅
#1415竹北集貨站1🔺雨潔
#2506新竹竹北莊敬六街1/敘思
#孫明益/新竹新馥7件
#1501新竹市經國路三段1/黃老師"""
    result = calculate(text, "PT")
    assert result["total_points"] == 8
    assert result["total_pieces"] == 18
    assert result["total"] == 2835


def test_phone_and_south_endpoint_case_is_4090_for_pt():
    text = """#1415竹北集貨站1 意玟
#1415竹北集貨站1 季亭
#1415竹北集貨站1 鈞蘋
#1613竹北集貨站1 心慧
#孫明益/新竹新馥17件+3桶
#1520忠孝東路四段1 上慈 🔺送達電話通知 0906139759
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


def test_phone_is_never_piece_count():
    text = "#1520忠孝東路四段1上慈 🔺送達電話通知 0906139759"
    _, stops, _ = parse_dispatch(text)
    assert len(stops) == 1
    assert stops[0]["pieces"] == 1


def test_regular_same_road_without_shared_identity_is_not_blindly_merged():
    text = """#1415竹北光明六路東二段1/Yawen葉
#1415竹北光明六路東二段1芝涵"""
    result = calculate(text, "PT")
    assert result["total_points"] == 2
    assert result["total_pieces"] == 2


def test_transfer_and_normal_tj_same_destination_are_one_point():
    text = """#TJ/#1507新竹東區北大路1+🔺特快
#TJ忠孝+收2+1*超件/花市中轉-新竹東區北大路"""
    result = calculate(text, "PT")
    assert result["total_points"] == 1
    assert result["total_pieces"] == 4


def test_regular_extra_piece_notation_is_added():
    text = "#TJ/#2506台中西區忠明南路1+2*超"
    result = calculate(text, "PT")
    assert result["total_points"] == 1
    assert result["total_pieces"] == 3


def test_full_time_does_not_stack_regions_without_endpoint():
    text = """#1311桃園正光路1娜家
#2506新竹竹北莊敬六街1敘思
#1415台中西屯福科路1依伶"""
    result = calculate(text, "正職")
    assert result["total_points"] == 3
    assert result["total_pieces"] == 3
    assert result["total"] == 600
    assert result["price_status"] == "待確認打底"
    assert not any("打底（" in line["name"] for line in result["lines"])


def test_full_time_uses_one_explicit_trip_endpoint_base():
    text = """#1311桃園正光路1娜家
#2506新竹竹北莊敬六街1敘思
#1415台中西屯福科路1依伶
終點=中部"""
    result = calculate(text, "正職")
    assert result["total"] == 1100
    bases = [line for line in result["lines"] if "打底" in line["name"]]
    assert len(bases) == 1
    assert bases[0]["amount"] == 500
