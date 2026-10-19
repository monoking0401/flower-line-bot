import pytest
from dispatch_formats import dispatch_format_reply


@pytest.mark.parametrize('alias,airport', [('桃園','桃園機場'),('台北','台北松山機場'),('台中','台中清泉崗機場'),('高雄','高雄小港機場'),('清泉崗','台中清泉崗機場'),('小港','高雄小港機場'),('松山','台北松山機場')])
@pytest.mark.parametrize('direction', ['接機','送機'])
def test_airport_and_direction(alias, airport, direction):
    text = dispatch_format_reply(f'派車格式 司機 {direction}{alias}')
    assert airport in text
    route = next(line for line in text.splitlines() if line.startswith('📍'))
    if direction == '接機':
        assert route.index(airport) < route.index('→')
        assert '落地' in text and '預計上車' in text and '起飛' not in text
    else:
        assert route.index(airport) > route.index('→')
        assert '起飛' in text and '出發' in text and '落地' not in text
    assert text.endswith('小天派單 標記+私')
    assert '姓名' not in text and '電話' not in text
    assert '1200' not in text and '8/14' not in text


def test_shortcuts_unknown_and_regular_chat():
    assert dispatch_format_reply('派車格式 送清泉崗') == dispatch_format_reply('派車格式 司機 送機清泉崗')
    assert '台中清泉崗機場' in dispatch_format_reply('派車格式　司機　接機臺中。')
    assert '上車地址 → 下車地址' in dispatch_format_reply('派車格式 司機 接駁')
    assert '支援' in dispatch_format_reply('派車格式 司機 送機未知')
    for text in ('不要派車格式', '我想問指令', '司機送清泉崗', None):
        assert dispatch_format_reply(text) is None
    assert '選公司 1' not in dispatch_format_reply('指令')
    assert '選公司 1' in dispatch_format_reply('派車單功能')
    assert '派車格式 司機 接機松山' in dispatch_format_reply('指令')
    assert dispatch_format_reply('派單格式') == dispatch_format_reply('派車格式')
