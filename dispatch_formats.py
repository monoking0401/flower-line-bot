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

COMMAND_HELP = '''小天派單機器人｜指令

【群組、私訊都可用】
派車格式 司機 送機清泉崗：司機群組簡潔範本
派車格式 司機 接機桃園：接機範本
派車格式 司機 接駁：一般接駁範本
機場可換桃園／松山／清泉崗／小港，接機送機皆可。
送機格式／接機格式／接駁格式：給客人填寫的詳細資料表
用車格式：列出客人資料表
指令：顯示本選單

【電子派車單｜機器人私訊操作】
先在 APK「製作派車單」連結 LINE 會員。
製單說明：完整製單步驟
公司清單 → 選公司 1
製單：下一行貼完整客人資料
行程 YYYY-MM-DD：查已授權行事曆，可加客人關鍵字
選行程 1：帶入行程
司機清單 → 選司機 1／儲存司機
承租人同乘客：帶入乘客姓名
修改：下一行貼要改的欄位
預覽／派車單／租賃單：輸出圖片及 PDF
查單 → 選單 1
發送 → 確認發送：將成品送至已綁定群組
發送狀態／取消

【群組綁定】
在 APK 取得綁定碼，再依畫面貼到指定群組。
群組簡潔貼單與電子派車單是兩個獨立功能。'''


def dispatch_format_reply(value):
    if not isinstance(value, str) or len(value) > 200:
        return None
    command = unicodedata.normalize('NFKC', value).strip().rstrip('。！!：:').replace('臺', '台')
    if command in ('指令', '指令清單', '功能', '功能清單'):
        return COMMAND_HELP
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
