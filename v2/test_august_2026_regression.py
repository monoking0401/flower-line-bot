import pytest

from flower_engine_pt_south import calculate


# Core rates confirmed from August boss statements.
def general(points, pieces, buckets=0):
    return points * 200 + max(pieces - points, 0) * 100 + buckets * 50


def north(points, pieces):
    return points * 135 + max(pieces - points, 0) * 100


# ===== 劉仲偉 / PT：8 月所有已有正式日結的日期 =====
# 樓層費、中轉薪資、特別勤務等非核心項目，只拿老闆正式日結數字核帳；
# 計算引擎不從派單文字自行猜這些人工加給。
PT_LEDGER = {
    "08/05": (
        500 + general(5, 17, 4) + 1200 + 900 + 100,
        5100,
    ),
    "08/06": (
        300 + general(3, 22, 2),
        2900,
    ),
    "08/07": (
        500 + general(5, 20, 1),
        3050,
    ),
    "08/08": (
        500 + general(9, 13),
        2700,
    ),
    "08/11": (
        500 + general(5, 5) + 400 + 400 + 700,
        3000,
    ),
    "08/13": (
        500 + general(6, 19),
        3000,
    ),
    "08/17": (
        300 + north(1, 1) + general(1, 25, 2)
        + 500 + general(12, 16),
        6435,
    ),
    # 老闆明確確認：只有集貨/集運、沒有宅配，所以不打底。
    "08/18": (
        general(3, 18),
        2100,
    ),
    "08/19": (
        500 + north(1, 2) + general(7, 11) + 465,
        3000,
    ),
    "08/21": (
        300 + north(1, 1) + general(7, 17),
        2835,
    ),
}


@pytest.mark.parametrize(
    "date,calculated,official",
    [(d, *values) for d, values in PT_LEDGER.items()],
    ids=list(PT_LEDGER),
)
def test_pt_official_august_daily_ledger(date, calculated, official):
    assert calculated == official, date


def test_pt_boss_combined_statement_0817_0818_is_8535():
    assert PT_LEDGER["08/17"][1] + PT_LEDGER["08/18"][1] == 8535


def test_pt_boss_combined_statement_0819_0821_is_5835():
    assert PT_LEDGER["08/19"][1] + PT_LEDGER["08/21"][1] == 5835


# ===== 林岳賢 / 正職：8 月所有目前找到的正式日結日期 =====
FULLTIME_LEDGER = {
    "08/04": (
        500 + general(12, 22) + 100,
        4000,
    ),
    "08/06": (
        500 + general(12, 18),
        3500,
    ),
    "08/11": (
        1000 + general(8, 25) + 100 + 600,
        5000,
    ),
    "08/13": (
        300 + north(5, 5) + 200 + general(2, 2)
        + 100 + 320 + 505,
        2500,
    ),
    # 正職同一趟可同時有台南 + 高雄打底。
    "08/14": (
        400 + 800 + 1000 + general(9, 27) + 100 + 250,
        6150,
    ),
    # 正職同一趟可同時有桃園 + 新竹 + 中部打底。
    "08/15": (
        100 + 300 + 500 + general(16, 26) + 300,
        5400,
    ),
    "08/17": (
        600 + 500 + general(7, 10) + 100 + 550 + 1000,
        4450,
    ),
}


@pytest.mark.parametrize(
    "date,calculated,official",
    [(d, *values) for d, values in FULLTIME_LEDGER.items()],
    ids=list(FULLTIME_LEDGER),
)
def test_fulltime_official_august_daily_ledger(date, calculated, official):
    assert calculated == official, date


def test_fulltime_boss_combined_statement_0813_0814_is_8650():
    assert FULLTIME_LEDGER["08/13"][1] + FULLTIME_LEDGER["08/14"][1] == 8650


def test_fulltime_boss_combined_statement_0815_0817_is_9850():
    assert FULLTIME_LEDGER["08/15"][1] + FULLTIME_LEDGER["08/17"][1] == 9850


# ===== 真實派單原文直接餵目前正式計算引擎 =====
RAW_PT_CASES = {
    "08/06": (
        """#1415竹北集貨站1🔺瑜萱
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
#孫明益/新竹新馥11件+2桶""",
        (3, 22, 2, 2900),
    ),
    "08/07": (
        """#1114竹北集貨站1🔺意玟🔺站主送店內
#1415竹北集貨站1🔺如慧
#1108竹北集貨站1🔺春玥
#孫明益/新竹新馥10件+1桶
#1415台中集貨站1🔺其恩
#1415台中集貨站1🔺妘芸
#1712台中集貨站2🔺台中吳
#1613台中集貨站1🔺心嫻
#1415台中西屯市政北一路1如妙🔺中午前
#1311台中西屯杏林路1銖禾禾""",
        (5, 20, 1, 3050),
    ),
    "08/13": (
        """#1114竹北集貨站1🔺意玟🔺站主請送入店內
#1712台中集貨站2🔺台中吳
#1415台中集貨站1🔺侑靜
#1415台中集貨站3🔺紹成
#1415台中集貨站4🔺曼郁
#1415台中集貨站1🔺依琹
#1711台中集貨站1🔺林其
#2107台中南屯大墩六街1穎宣
#1415台中烏日高鐵東一路3冠瑩
#Tiffeny/#1421台中中清路二段1
#1501台中北屯崇德路三段1詠潔""",
        (6, 19, 0, 3000),
    ),
    "08/18": (
        """#1415竹北集貨站1🔺劉品毅
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
#1507彰化集貨站1🔺亮彤""",
        (3, 18, 0, 2100),
    ),
    "08/21": (
        """#1320中壢延平路2老k🔺急件
#1511中壢民族路1/謝淑文
#曾聰明花坊#1709楊梅自立街2🔺特快
#曾聰明花坊#1320楊梅自立街1
#1612新店北新路二段1小植光
#1415竹北集貨站1🔺雅梅
#1415竹北集貨站1🔺雨潔
#2506新竹竹北莊敬六街1/敘思
#孫明益/新竹新馥7件
#1501新竹市經國路三段1/黃老師""",
        (8, 18, 0, 2835),
    ),
}


@pytest.mark.parametrize(
    "date,text,expected",
    [(d, *values) for d, values in RAW_PT_CASES.items()],
    ids=list(RAW_PT_CASES),
)
def test_real_august_pt_dispatch_through_engine(date, text, expected):
    result = calculate(text, "PT")
    actual = (
        result["total_points"],
        result["total_pieces"],
        result["total_buckets"],
        result["total"],
    )
    assert actual == expected, date

    if date == "08/18":
        assert not [line for line in result["lines"] if "打底" in line["name"]]


def test_fulltime_contract_two_region_bases_same_trip():
    text = """#1415台南永康中華路1甲
#1415高雄左營博愛路1乙"""
    result = calculate(text, "正職")
    bases = [line for line in result["lines"] if "打底" in line["name"]]
    assert [line["amount"] for line in bases] == [800, 1000]


def test_fulltime_contract_three_region_bases_same_trip():
    text = """#1415桃園中壢元化路1甲
#1415新竹東區民權路1乙
#1415台中西屯福科路1丙"""
    result = calculate(text, "正職")
    bases = [line for line in result["lines"] if "打底" in line["name"]]
    assert [line["amount"] for line in bases] == [100, 300, 500]
