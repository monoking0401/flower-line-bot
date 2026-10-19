"""Local, stateless copy-and-fill templates for explicit LINE commands."""
import re
import unicodedata

AIRPORTS = {
    '桃園': ('桃機', '桃園機場'), '桃園機場': ('桃機', '桃園機場'),
    '桃機': ('桃機', '桃園機場'),
    '台中': ('清泉崗', '台中清泉崗機場'), '台中機場': ('清泉崗', '台中清泉崗機場'),
    '清泉崗': ('清泉崗', '台中清泉崗機場'), '清泉崗機場': ('清泉崗', '台中清泉崗機場'),
    '中機': ('清泉崗', '台中清泉崗機場'),
    '台北': ('松山', '台北松山機場'), '台北機場': ('松山', '台北松山機場'),
    '松山': ('松山', '台北松山機場'), '松山機場': ('松山', '台北松山機場'),
    '松機': ('松山', '台北松山機場'),
    '高雄': ('小港', '高雄小港機場'), '高雄機場': ('小港', '高雄小港機場'),
    '小港': ('小港', '高雄小港機場'), '小港機場': ('小港', '高雄小港機場'),
}

FORMAT_HELP = '''司機派單範本（複製後填寫）
派車格式 司機 送機清泉崗
派車格式 司機 接機桃園
派車格式 司機 送機松山
派車格式 司機 接機小港
派車格式 司機 接駁

也可簡寫：派車格式 送清泉崗
支援接機／送機；台中＝清泉崗、台北＝松山、高雄＝小港、桃園＝桃機。
回覆的是空白文字範本，填好後自行貼單。'''

COMMAND_HELP = '小天派單機器人｜指令\n每行是一條指令，可複製後單獨傳送。\n\n【司機派單範本】\n派車格式 司機 送機桃園\n派車格式 司機 接機桃園\n派車格式 司機 送機松山\n派車格式 司機 接機松山\n派車格式 司機 送機清泉崗\n派車格式 司機 接機清泉崗\n派車格式 司機 送機小港\n派車格式 司機 接機小港\n派車格式 司機 接駁\n\n【客人填寫資料表】\n送機格式\n接機格式\n接駁格式\n\n【查看格式選單】\n派車格式\n用車格式\n\n【電子派車單操作說明】\n派車單功能\n\n【查看本指令清單】\n指令'

DOCUMENT_HELP = '電子派車單功能\n以下操作請在機器人私訊使用；每行指令可單獨複製。\n先在 APK「製作派車單」連結 LINE 會員，使用畫面產生的製單綁定碼。\n\n【選公司】\n公司清單\n選公司 1\n\n【建立單據】\n製單\n（「製單」下一行貼完整客人資料，一起傳送）\n\n【匯入行事曆】\n行程 今天\n行程 明天\n行程 後天\n行程 2026-10-20\n行程 2026-10-20 客人關鍵字\n選行程 1\n（日期、關鍵字與編號可自行替換）\n\n【常用司機】\n司機清單\n選司機 1\n儲存司機\n\n【承租人】\n承租人同乘客\n\n【修改資料】\n修改\n（下一行貼「欄位：內容」，一起傳送；例如服務據點、付款方式、聯繫方式）\n\n【圖片與 PDF】\n預覽\n派車單\n租賃單\n正式輸出\n（正式輸出同派車單；租賃單需完整資料）\n\n【歷史單據】\n查單\n選單 1\n\n【發送至已綁定群組】\n發送\n確認發送\n發送狀態\n（先傳「發送」確認目的群組，再傳「確認發送」）\n\n【結束操作】\n取消\n\n【重新查看說明】\n派車單功能\n製單說明\n\n編號依當次選單替換；群組綁定碼由 APK 產生。'

def dispatch_format_reply(value):
    if not isinstance(value, str) or len(value) > 200:
        return None
    command = unicodedata.normalize('NFKC', value).strip().rstrip('。！!：:').replace('臺', '台')
    if command in ('指令', '指令清單', '功能', '功能清單'):
        return COMMAND_HELP
    if command in ('派車單功能', '製單說明'):
        return DOCUMENT_HELP
    command = re.sub(r'^派單格式(?=\s|$)', '派車格式', command)
    if not re.match(r'^派車格式(?:\s|$)', command):
        return None
    parts = re.fullmatch(r'派車格式\s+(?:司機\s+)?(.+)', command)
    if not parts:
        return FORMAT_HELP
    task = re.sub(r'\s+', '', parts[1])
    if task in ('接駁', '交通接駁', '一般接駁'):
        title, clock, route, flight = '交通接駁', '出發', '上車地址 → 下車地址', ''
    else:
        match = re.fullmatch(r'(接機|送機|接|送)(.+)', task)
        if not match or match[2] not in AIRPORTS:
            return FORMAT_HELP
        pickup = match[1].startswith('接')
        short, airport = AIRPORTS[match[2]]
        title = ('接' if pickup else '送') + short
        clock = '預計上車' if pickup else '出發'
        route = airport + ' → 下車地址' if pickup else '上車地址 → ' + airport
        if short == '桃機':
            route = route.replace(airport, airport + '（T1／T2）')
        flight = '\n✈️ 航班：____｜__:__ ' + ('落地' if pickup else '起飛')
    return (f'🗓 __/__（__）{title}\n⏰ __:__ {clock}{flight}\n'
            f'📍 {route}\n🚐 8～9座\n👥 __人｜🧳 __件行李\n'
            '💵 車資：$____（現金／匯款／月結）\n\n小天派單 標記+私')
