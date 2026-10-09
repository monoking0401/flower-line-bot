# 2026-10-10 小天報單機器人專用入口

使用者已停止跑花市，授權沿用 @017pcooo，指定新的 LINE 顯示名稱「小天報單機器人」。
LINE 顯示名稱必须由 Official Account Manager 修改，再用官方 bot/info 核對；改程式標題不代表 LINE 已改名。
既有花市原碼、v2、報價服務原碼保留作歷史。main.py 固定使用 dispatch_relay.app。

- 花市計價／自動回覆已退休，不再提供此帳號的啟動入口。
- FLOWER_DISPATCH_RELAY_ENABLED 為過期設定；任何值或未設定，都不會恢復花市報價。
- APK 的轉送開關仍能隨時停止這支手機發起新的轉送，關閉不會啟動花市功能。
- 健康資訊 service=xiaotian-dispatch-bot、version=1.0.1，是後端識別，並非 LINE 顯示名稱驗證。
- LINE_CHANNEL_SECRET／LINE_CHANNEL_ACCESS_TOKEN 沿用此服務既有秘密，沒有讀出／複製到另一服務。
- LINE_RELAY_BRIDGE_KEY：兩個伺服器共用獨立隨機密鑰，至少32字元；不得保存於Git／文件／APK。
- LINE_RELAY_BOT_ID：以原Token向官方 bot/info 實際核對後設定，不能拿Basic ID代替。

花市既有 /webhook URL 不變。LINE原簽章驗證後，僅背景轉交 #小天綁定 指令。
一般群聊、照片、位置、人名、會員原文都不經webhook鏡像至派車服務，不自動回复。
使用者在APK登入、綁定目的群一次，之後每次按確認轉送，由派車會員後端送來經HMAC驗證的有限操作。

橋接只接受群組摘要與群組文字push（1～2則，每則5000 UTF-16單位內，不截斷），不接受任意URL、好友清單、個人收件者或原生名片。
HMAC涵蓋時間／方法／路徑／完整body，±60秒；推送必須帶穩定X-Line-Retry-Key。
LINE受理不等於已送達或已讀。409只有官方接受header才視為已受理；不盲目重送。
綁定是短期記憶體，不是持久佇列；背景投遞失敗時在APK仍顯示等待，可重貼同一綁定指令或重產生碼。
原生名片仍未完成，不能拿名字或假名片替代。免費Render休眠仍可能延遲或逾時，正式會員營運需再決定常駐主機。
報價Bot的啟動指令 quote.main:app、憑證與程式均不更改；同庫main更新可能觸發它重新部署，需核對健康。
