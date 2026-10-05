# 情書｜六人宮廷密函 BOT

Python Telegram 群組遊戲。V2 改為 UNOBOT 類型的 Inline 圖片選牌，十張卡採用你提供的實體桌遊卡風格：金色雕花邊框、酒紅數字圓章、米白說明區與宮廷人物插畫。

採用新版 21 張牌的 2～6 人規則，預設 60 秒行動時間，可由房主以電腦補滿六人。圖片與字型已放在 assets，不需要另外購買繪圖 API 或在執行時產生圖片。

## Windows 最快啟動

1. 安裝 Python 3.12，安裝時勾選「Add Python to PATH」。
2. 解壓縮整個資料夾，不要只取出 bot.py。
3. 到 Telegram 的官方 @BotFather 使用 `/newbot` 建立 BOT 並取得 Token。
4. 雙擊 `start_windows.bat`。第一次會安裝套件並開啟 `.env`，把 `BOT_TOKEN=` 後面的範例換成你的 Token，儲存關閉。
5. 再執行一次 `start_windows.bat`；視窗保持開啟。
6. 在 BotFather 輸入 `/setinline`，選你的 BOT，輸入提示文字「選擇要打出的角色卡」。
7. 在 BotFather 輸入 `/setinlinefeedback`，選你的 BOT，設定 **100%**，讓點選圖片後能自動執行。
8. 私訊你的 BOT，按 START，輸入 `/setup`，等十張卡圖準備完成。只需一人初始化一次；遊戲不需要來回切私訊。
9. 把 BOT 加入群組，允許傳送訊息和圖片。一般群組不必給管理員權限，也不必關閉 Privacy Mode。
10. 在群組輸入 `/newgame`，房主自動入席。其他人直接按群組「加入遊戲」，房主按「開始遊戲」。單人試玩按「＋電腦補滿」。

Token 只填在自己的 `.env` 或部署平台環境變數，請勿貼到群組、GitHub 或聊天中。

## 群組操作流程

1. 輪到你時，在群組按「選牌出牌」。輸入框會自動帶入 BOT 名稱，出現只有你看得到的卡牌預覽。
2. 點要打出的角色圖片。程式確認本人、當前回合與牌張有效後，把那張卡公開發送到原本牌桌群組。
3. 守衛、祭司、男爵、王子、國王需要指定目標時，直接使用群組牌桌下方按鈕；守衛再按角色名稱猜牌。只有當前玩家可以操作。
4. 祭司偷看、男爵比牌及換牌結果：按「我的手牌／秘密情報」，以只有按鈕操作者看到的提示顯示。多筆情報可重複按鈕逐筆查看。
5. 大臣保留牌與回牌順序：再次開啟個人圖片選牌介面。群組只顯示完成選擇，不公開保留或放回的角色。

如果點圖後停留在「正在處理」，按該則訊息的「送出操作」即可補送。同一選擇即使收到兩次回報也只執行一次；沒有開啟 100% Inline feedback 時仍可用此按鈕完成，但建議先正確設定。

Telegram 的選牌結果預設一點就會送出；這版刻意把「預覽卡圖」與「真正送出的內容」分開：預覽是卡牌，剛點選的訊息是中性的處理提示，驗證成功後由 BOT 在牌桌發布合法出牌。舊卡或大臣的秘密選擇因此不會直接暴露在群組。

Telegram 的 inline 回報不提供實際收件群組 ID。因此所有選擇都綁定產生該選擇時的原始牌桌（訊息會顯示群組名稱）。即使把同一 inline 結果送到別處，操作仍只套用於原牌桌；請使用原群組的「選牌出牌」入口。權威結果只會發布在原牌桌。

- 群組牌桌原地更新：座位、行動者、牌庫、好感、保護、出局與棄牌。`/status` 可把牌桌重新送到底部。
- 每次行動共 60 秒，包括選目標、猜牌及大臣後續選擇；逾時由簡單 AI 代打。
- 每局結束由房主按「下一局」。整場結束可重新開桌，房主自動加入，其餘玩家重新入席。
- 一位真人同時只能在一桌；不同群組可以各開一桌。
- 私訊 `/hand` 仍保留圖片加按鈕備援。平常不會主動傳送私人手牌到私訊。
- 圖片面板的排列由 Telegram 客戶端決定，手機和桌面可能不同；不是自製 Mini App。

## 指令

| 指令 | 用途 |
|---|---|
| `/newgame` | 在群組開桌 |
| `/hand` | 群組開啟個人選牌；私訊為備援手牌 |
| `/setup` | 私訊初始化圖片；`/setup refresh` 重新上傳 |
| `/status` | 群組重新顯示牌桌 |
| `/rules` | 完整中文角色說明 |
| `/cancel` | 房主取消本桌 |

## 規則版本

這是支援六人的 21 張新版，不是 16 張四人版或 Premium 八人版。包含間諜 0、大臣 6，國王／女伯爵／公主分別是 7／8／9。

勝利門檻：2 人 6 枚、3 人 5 枚、4 人 4 枚、5～6 人 3 枚好感。每局最高持牌同分時各得一枚，不採用舊版的棄牌加總破同分。間諜只檢查仍存活玩家，且最多額外一枚。可同時出現多位整場贏家。

自訂部分：首局先手隨機、電腦玩家、自動逾時操作，以及每局由房主按鈕開局。下一局從上一局勝者中隨機選先手。電腦是簡單策略，並非高難度對手。

規則核對來源：[Z-Man 官方產品頁](https://www.zmangames.com/game/love-letter/)及其[官方說明書](https://cdn.svc.asmodee.net/production-zman/uploads/2026/04/LL_Rulebook_with_Bag.pdf)。遊戲原作：Seiji Kanai。本專案為非官方個人遊玩實作，未附原版掃描卡圖；角色插畫為獨立製作。

## 一般安裝與部署

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
# 複製 .env.example 為 .env 並填入 Token
python bot.py
```

程式使用 long polling，不需要公開網址、HTTPS 或 cloudflared。同一 Token 同時只能跑一個實例；不要在本機和主機同時啟動，也不要啟用多 worker。

主機設定：Python 3.12；Build command `pip install -r requirements.txt`；Start command `python bot.py`。也附 Dockerfile。使用環境變數 `BOT_TOKEN`、`TURN_SECONDS=60`、`DATA_PATH=/data/games.sqlite3`。若平台需要網頁健康檢查，設定 `PORT=10000`，GET `/` 會回應程序存活狀態；它不代表 Telegram 網路必定可達。

對於 Render 等主機，選擇能持續運行的 worker 或 web service，並把 DATA_PATH 指向持久磁碟；會休眠的服務不能保證即時回應與倒數計時。未掛載持久磁碟時，重新部署可能清空進度。主機方案與介面可能變動，請依平台當下設定操作。

SQLite 會在每個操作後儲存牌桌、私人手牌、計分與大臣操作中間狀態。重啟可恢復，當前玩家重新獲得完整操作時間。資料庫含私人手牌，請限制主機檔案權限；不要把 data 資料夾公開。

## 設定

| 變數 | 預設 | 說明 |
|---|---|---|
| BOT_TOKEN | 必填 | BotFather Token |
| TURN_SECONDS | 60 | 行動秒數，最短 15 秒，例如可改成 90 |
| DATA_PATH | data/games.sqlite3 | SQLite 檔案位置 |
| PORT | 不啟用 | HTTP 健康檢查通訊埠 |

## 圖片與檔案

- `assets/physical_cards.png`：依使用者實體卡參考重新繪製的十角色卡圖集。
- `assets/fonts/`：附可重散布的 Noto 中文字型及授權文字，跨 Windows／Linux 可渲染中文。
- `render.py`：程式排版中文角色名稱、數字、能力說明，不依賴繪圖模型生成文字。
- `preview/inline_group_mockup.png`：群組圖片選牌操作示意，非 Telegram 實測截圖。
- `preview/physical_style_preview.png`：實體卡風格近看預覽。
- `preview/group_table.png`：程式實際產生的群組圖片示範。
- `preview/private_hand.png`：程式實際產生的私訊手牌圖片示範。
- `preview/all_characters.jpg` 與 `card_0.png`～`card_9.png`：完整角色卡面。
- `engine.py`：純規則引擎；`bot.py`：Telegram；`storage.py`：保存進度；`inline_ui.py`：個人圖片選牌、圖片快取及選擇驗證。

預覽是範例資料渲染，不是真人 Telegram 實測截圖。私訊圖及群組圖都會隨遊戲狀態重畫。

## 驗證與限制

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python make_preview.py
python make_inline_preview.py
```

目前共 42 項測試，包含規則邊界、SQLite 還原、群組操作、秘密提示、舊選牌拒絕、錯誤玩家拒絕、選牌回報與備援按鈕防重複、大臣不洩漏牌張、圖片快取綁定 BOT，以及 1,000 場 2～6 人模擬整場對局的牌張守恆檢查。Telegram 傳送層使用 mock 測試；尚未填入真實 Token 在群組進行端到端連線測試。

若沒有圖片選牌：先確認 BotFather `/setinline` 已開啟，房主已完成 `/setup`。圖片失效可私訊 `/setup refresh`。若點圖沒有自動出牌，確認 `/setinlinefeedback` 為 100%，或按「送出操作」。群組圖片消失用 `/status`。出現 Conflict 通常是相同 Token 跑了兩個程序。若暫時斷線，狀態先保存，圖片可用上述指令重新取得；逾時代打仍會依主機運行狀況執行。

## 更新舊版

停止舊程序後，以本完整包取代程式及 assets；保留你自己的 `.env` 和 data 資料夾，再啟動。新增 SQLite 資料表及遊戲欄位會自動相容舊資料。第一次使用新版請執行 `/setup`，新版圖片快取不會沿用舊圖。沒有持久磁碟的主機重新部署後，可能要重新 `/setup`。

## 插畫製作紀錄

使用內建 image generation，以使用者提供的三張實體卡照片為主要風格／人物設計參考，重新繪製乾淨的 5 欄 2 列圖集。金色雕花邊框、酒紅圓章、米白卡紙、宮廷插畫；圖集保留空白文字區，繁體中文名稱、數字、能力文字由程式使用 Noto Serif TC 字型排版。未直接裁切、附上或重新散布使用者的來源照片。

角色名稱依參考統一為：0 間諜、1 守衛、2 祭司、3 男爵、4 侍女、5 王子、6 大臣、7 國王、8 女伯爵、9 公主。

Inline 技術依據：[Telegram Inline Bots](https://core.telegram.org/bots/inline)、[InlineQueryResultCachedPhoto](https://core.telegram.org/bots/api#inlinequeryresultcachedphoto)、[answerCallbackQuery](https://core.telegram.org/bots/api#answercallbackquery)。
