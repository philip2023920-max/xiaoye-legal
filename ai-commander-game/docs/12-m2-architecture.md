# 12 M2 參謀長接入＋玩家接管：選型、決策、施工單草案

> 文件狀態：✅ v0.2（2026-11-04，D23～D29 老闆「全照建議」→ ADR-0015；施工單 16～21 已建檔）｜對應心智圖節點：`6. 里程碑 → M2`、`5. 技術架構 → 參謀長服務`
> M2 的 Stage 2 產出：七個待拍板決策（D23～D29，附建議答案）、架構、施工單草案 16～21。老闆拍板後寫 ADR-0015、開施工單 16。

## 1. 先講結論（建議答案）

| # | 決策 | 建議 | 一句話理由 |
|---|---|---|---|
| D23 | Godot 怎麼接參謀長 | **本機 Python「參謀長服務」**：`chief serve`（標準庫 HTTP，JSON），Godot 用 `OS.create_process` 啟動、`HTTPRequest` 呼叫 | M0 的閘道、驗證器、準則、戰例庫、戰報卡**一行不改**全部重用（ADR-0011）；沙盒已實測 Godot 無頭 ↔ Python 往返與子程序啟動 |
| D24 | 決策節拍 | **固定 20 秒＋事件觸發**（接觸、據點易手、潰散、殲滅），事件觸發與上次至少隔 8 秒；參謀長思考時**遊戲不暫停**，HUD 顯示「思考中 n 秒」，命令回來才套用；60 秒沒回覆記「無回應」 | PRD F2「20 秒＋關鍵事件」；即時制不等 AI（ADR-0005）；暫停開關留 M3 |
| D25 | 金鑰與設定 | 設定頁選**供應商、模型、語言、預算、思考深度**，存 `user://settings.json` 並送服務；**金鑰仍在服務端 `.env`**，設定頁只顯示「已設定／未設定」 | 不把金鑰經過遊戲程序；加密儲存留 M3（PRD F5 的「存本機加密」） |
| D26 | UI 工具 | **Godot 內建 Control**（Tree、ItemList、RichTextLabel、Button、Panel）＋內建主題 | 零依賴；主題潤飾留 M3 |
| D27 | 多語 | **UI 字串表** `godot/i18n/ui.csv`（zh-TW／zh-CN／en 三欄一次寫齊）→ `TranslationServer`；參謀長的語言由設定頁傳給服務 | D7 三語；Godot 內建機制 |
| D28 | 串流 | **M2 不串流**（整包回來）；PRD「首字 < 2 秒」改以「思考中指示 ≤ 0.5 秒出現、命令套用時標示延遲秒數」交代 | 串流要改三個 adapter；先把迴圈接通；列 M3 |
| D29 | 接管的選取粒度 | **排與連**（點側欄的樹或點地圖上的排）；目標分區用點地圖；班／旅／軍團留對應規模（ADR-0008） | 會戰規模的最小行動單位是排；M1 沒有班級節點 |

2026-11-04 老闆「全照建議」，已寫 ADR-0015。

## 2. 架構

```
Godot（畫面、節拍、推翻 UI、側欄、AAR 畫面、設定）
   │ HTTP JSON（127.0.0.1:8765）                 ▲ 戰情板：Godot 每 0.1 秒寫 user://board.json（M1 已做）；
   ▼                                            │ 節拍時把整份板放進 /tick 的請求裡（服務不用讀檔）
Python 參謀長服務 chief serve（m0/chief/serve.py，標準庫 http.server，不加依賴）
   ├─ /session/start   board、參謀長包／準則、供應商、模型、語言、預算 → 開局引用句
   ├─ /tick            {t, board} → {turn, assessment, orders(驗證放行), rejected, usage, cost, latency, error, outcomes}（退回回饋由服務自己帶到下一拍）
   ├─ /override        {unit_id, player_order, ai_order?, board?} → 先驗命令再記錄；推翻後 ≥20 秒的第一個 tick 判後果（§9）；已直轄單位再改令不算
   ├─ /battle/end      {board, result} → 戰報卡（card）、徽章、未判定數
   ├─ /aar/line  /aar/discuss  /aar/propose  /aar/adopt  /aar/undo   重用 report／discussion／doctrine／evals
   ├─ /status          供應商、模型、本場費用、今天／本月（ledger）、預算狀態
   └─ /settings        改供應商／模型／語言／預算／effort（重建閘道）
```

- **重用**：`play.py` 的每回合流程拆成 `chief/bridge.py`（純函式、無終端機）；`chief play` 與服務共用它。FakeGateway 讓 Godot 的無頭整合測試不花錢、可在沙盒跑。
- **Godot 端**：`scripts/chief/chief_client.gd`（啟動子程序、健康檢查、請求佇列、逾時）、`scripts/chief/tick_scheduler.gd`、`scripts/ui/{sidebar,override_panel,aar_screen,settings,cost_hud}.gd`。
- **推翻流程**：玩家點排（地圖）或排／連（側欄樹）→ 面板：六種任務＋「點地圖選目標」→ 送 `Orbat.apply_orders(side="us", issuer="player")` 並標 `controlled_by=player`（直轄：參謀長不得下令，驗證器 V2 在服務端擋）→ POST /override；「放手」把 `controlled_by` 改回 ai。推翻後果由服務在推翻後 ≥20 秒的第一個 tick 判（§9），回傳到側欄事件流顯示 👍👎➖；/override 要在接管當下、下一拍之前送，板上要標好 `controlled_by`，服務才分得出「接管」與「已直轄再改令」。
- **戰後**：導演結束 → POST /battle/end → AAR 畫面：戰報卡（三幕、徽章、一句話）→ 討論（三個快速回覆按鈕＋輸入框，最多三回合）→ 準則 diff（採納／不採納／撤銷）→ 回歸結果（退步自動回滾的訊息）。自動模式（沒有推翻）只出卡。
- **費用 HUD**：每個 tick 回來更新本場費用；每 30 秒 GET /status 更新今天／本月；80% 提醒、100% 參謀長暫停（服務端已有）。
- **開發期啟動**：Godot 從 `godot/` 執行 `uv run chief serve --port 8765`（工作目錄 `../m0`，讀 `.env`）；找不到 uv 或 10 秒內服務沒起來 → HUD 顯示「參謀長服務沒起來」並提供「離線模式」（M1 的劇本／空白鍵）。M3 打包時再決定凍結 Python 的方式。

## 3. 施工單草案（老闆拍板後正式建檔）

| # | 施工單 | 對應 | Blocked by | 30 秒驗收 |
|---|---|---|---|---|
| 16 | 參謀長服務 `chief serve`：端點如上、`bridge.py` 抽出、FakeGateway 可跑、M0 測試 | T2.2 | — | `uv run chief serve --provider fake` → curl /tick 回命令 |
| 17 | Godot 節拍與客戶端：啟動服務、健康檢查、20 秒＋事件節拍、/tick 套用命令、退回回饋、思考中指示、無回應處理；**跨程序無頭整合測試**（fake 供應商打完 5 分鐘） | T2.1、T2.2 | 16 | F5 → 參謀長自己下令、事件流有「參謀長令…」 |
| 18 | 戰情板側欄：部隊樹（戰力／狀態／任務／直轄）、事件流、參謀長評估與最近命令、據點、天氣、費用 | T2.3 | 17 | F5 右側看到側欄即時更新 |
| 19 | 推翻與接管：選排／連、六任務面板、點地圖選目標、接管／放手、直轄標記（環色）、/override、後果顯示 | T2.4 | 18 | 點一個排改令 → 參謀長下回合不碰它、30 秒後事件流出現 👍／👎 |
| 20 | 戰後 AAR 畫面：戰報卡、徽章、討論三回合、採納／撤銷、回歸結果 | T2.5、T2.8 | 19 | 打完一場 → 卡 → 三個快速回覆 → 採納 → `doctrine.md` 變了 |
| 21 | 設定頁、費用 HUD、三語字串表：供應商／模型／語言／預算／effort；本場／今天／本月；80%／100% 警示；UI 全部走字串表 | T2.6、T2.7 | 17 | 設定頁改成 Anthropic Haiku → 下一 tick 真的用 |

M2 驗收（PRD 成功定義）：老闆本機用 Haiku 打完一場（含至少一次推翻與戰後採納），`chief stats` 看到那場；推翻率與費用都在卡上。

## 4. 沙盒探針（2026-11-04）

- Godot 4.7.2 無頭 `HTTPRequest` POST JSON 到本機 Python `ThreadingHTTPServer`：往返成功（exit 0）。
- `OS.create_process("python3", …)`：可啟動、`is_process_running` 為真、可 `kill`。
- 結論：D23 的路徑在沙盒可整合測試；真模型只在老闆本機。

## 5. 風險

- 服務與遊戲是兩個程序：遊戲當掉服務會留著（客戶端退出時 POST /shutdown 或 kill；服務自己 10 分鐘沒請求就退出，處理中的請求不算閒置）。服務只綁本機、`--token` 由 Godot 產生亂數傳入並帶 `X-Chief-Token`；不帶 token 時同機任何程式都能叫它。
- 參謀長 20 秒一次、每次約 1.5K token：Haiku 一場 5 分鐘約 15 次呼叫，費用與 M0 同量級（< US$0.05）。
- 推翻的後果判定沿用 §9：秒制板在推翻後至少 20 秒的第一拍判（事件拍離推翻太近不判，避免系統性偏 👍）；M1 的分區看位置。
