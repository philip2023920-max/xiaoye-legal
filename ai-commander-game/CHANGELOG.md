# 變更紀錄（心智圖與文件同步日誌）

每次依心智圖施工後，在此新增一條：日期｜動了哪些節點｜改了哪些檔案。

## 2026-11-04（第三十三次）— 施工單 16 三審第一輪 18 項全部修正
- `chief/bridge.py`：`aar_closed`（adopt／skip 只做一次，之後 409）、`/override` 先驗命令、已直轄不算推翻（`counted`、`player_units`）、`ai_order` 沿上級鏈取最近一拍、§9 秒制板 ≥20 秒才判（`JUDGE_DELAY_S`）、`EndResult` 先驗、拍數不動、每拍同組鍵、`close()` 補寫戰例、`duration_s` 從第一次互動起算、settings 的 `aar_*` 獨立
- `chief/serve.py`：`/session/start` 白名單＋準則路徑限工作目錄＋裸板自動包、`--token`／`X-Chief-Token`（401）、`in_flight` 閒置計時、409／404／405／411／413、斷線不噴 traceback；`chief serve --token`；`gateway.make_gateway("anthropic")` 缺金鑰直接 ValueError
- `chief/prompts.py`：秒制板提示改「Decision n (t=… s)」＋「Time left … of 300」
- 文件：規則 §9 補秒制判定時點、§16 合約全面改寫；docs/12 §2 端點欄位修正；施工單 16 驗收腳本第 1 行修正＋審查紀錄
- 測試：`tests/test_service.py` 9 → 21；M0 測試 188 → 199（198 過＋1 skip）

## 2026-11-04（第三十二次）— M2 拍板（ADR-0015）、施工單 16～21 建檔、16 參謀長服務（程式完成）
- 老闆「全照建議」→ `docs/adr/0015-m2-chief-service.md`；決策第六輪 ✅；施工單 16～21 建檔
- `chief/bridge.py`：`ChiefSession`（start／tick／override／end／aar_line／discuss／propose／adopt／skip／undo／status／settings），把 play.py 的每回合與戰後流程拆成不靠終端機的方法；`discussion.system_prompt`、`play.regression_check_core` 抽出共用
- `chief/serve.py`：標準庫 HTTP 服務（13 個端點、請求序列化、idle-exit、shutdown、人話錯誤）；`chief serve` 子命令；規則 §16 服務合約
- `tests/test_service.py` 9 個（流程、後果 👍、預算暫停、設定切換、自訂準則、HTTP 往返、CLI idle-exit）；M0 測試 179 → 188

## 2026-11-04（第三十一次）— 老闆「下一步」：M2 Stage 2 選型
- 沙盒探針：Godot 4.7.2 無頭 `HTTPRequest` ↔ 本機 Python `ThreadingHTTPServer` JSON 往返、`OS.create_process` 啟動子程序，都通
- `docs/12-m2-architecture.md`：D23～D29 建議答案（本機 Python 參謀長服務重用 M0 全部、20 秒＋事件節拍不暫停、金鑰留 .env、內建 UI、三語字串表、不串流、排與連接管）、服務端點、Godot 端模組、施工單草案 16～21、風險
- 決策紀錄第六輪；路線圖 T2.x 對應施工單；心智圖 M2 節點展開；回寫 Artifact 資料庫

## 2026-11-04（第三十次）— 15 結案、M1 完成
- 老闆指出「在 RX 7900 XTX 上讀 FPS 沒有意義」：目標是 2018 內顯，高階機數字證明不了任何事。改記為「畫面側目標硬體未驗、負載極低判定風險低、有低階機再補」；CPU 側沙盒已驗
- M1 六張施工單全部 ✅；驗收「5 分鐘會戰無 LLM 打完」老闆本機達成；M2 待老闆下令

## 2026-11-02（第二十九次）— 14 本機驗收通過（打完一場並回放）；施工單 15 效能（程式完成，待 FPS 讀數）
- 老闆本機 normal 一場：天氣三次切換、t6 敵機槍潰散我方取 C3、t7 敵取無人守的 B2、敵方 6:5 勝；`chief replay` 回放正確 → 14 ✅；M1 驗收「5 分鐘會戰無 LLM 打完」達成
- HUD 加 FPS 與人數；`-- stress=N` 壓力模式；`tools/bench.gd` CPU 基準（1 倍 126 人 0.34 ms/tick、5 倍 1.70、10 倍 3.78；預算 16.7）；`tests/test_perf.gd` 守門
- 路線圖 T1.1～T1.6 ✅、T1.7 待讀數；`docs/11` §6 效能實測
- 15 審查 10 項全部修正：壓力模式每倍 126 人（文件原寫 1,386 但程式 846）並自動關 V-Sync、HUD 幀時間、`test_perf` 不再造脫離的 SceneTree、bench 含每秒戰情板 hook 與 p99、方塊人共用網格與材質（畫面側最便宜的一招）

## 2026-11-02（第二十八次）— 12／13 本機驗收通過、D22 維持；施工單 14 五分鐘會戰（程式完成）
- 老闆本機 `chief show` 讀到 Godot 寫的板（t=45、命令、接觸、易手、交戰）→ 12／13 ✅；D22 老闆未反對 → 維持
- `scripts/battle/director.gd`：劇本排程（第 n 回合＝第 30(n−1) 秒）、天氣變化、結束判定、結果（M0 同欄位）、每 30 秒快照、`run_to_end`；`Battle` 加難度／我方劇本（命令列 `-- difficulty= friendly=`）、HUD 剩餘秒數與據點、結果畫面、R 重開；`tools/run_battle.gd`
- 三難度結果與 M0 §14 同趨勢且接近（easy 8:3 剩 7.02:1.79、normal 8:3 剩 6.70:4.34、hard 3:8 剩 6.16:4.98）；`tests/smoke_battle.gd` 14 項
- M0 `chief replay` 支援秒制快照並印 result.json 勝負；`m0/samples/godot_battle_sample/`（t0～t10＋result.json）＋測試；M0 測試 178 → 179
- 14 審查 9 項全部修正：開局清舊快照（回放拼接）、提早結束補最後快照、未知難度、結束那秒寫板、工具失敗 exit 1、命令列引數不污染測試、煙霧測試 14 → 24

## 2026-11-02（第二十七次）— 11 本機驗收通過；施工單 12 戰鬥解算、13 戰情板寫入（程式完成）
- 老闆本機 `test_orbat.gd` 50 項通過 → 11 ✅
- `scripts/combat/resolver.gd`：30 秒回合快照、每秒 1/30 傷害、迫砲鄰格、工兵本格、門檻與任務清空、射線；五組手算例在引擎重現（容差 1%）；§15 記下與 M0 的差異（落單殘排潰散後逃得掉）
- `Orbat`：結構化事件 {t, kind, text, unit, sector}、`set_conditions` 天氣事件、engaged 狀態推導、每秒 hook
- `scripts/core/board_writer.gd`：§6 歸屬、§2 視距敵情、Board v0.2、原子寫入；`Battle` 每 0.1 秒寫 `user://board.json`、HUD 加據點分、射線畫面；`tools/dump_board.gd`
- `m0/samples/godot_board_sample.json`＋`m0/tests/test_godot_board.py`（M0 Board 模型讀 Godot 的板、`chief show` 可渲染、GODOT_BIN 現場跑）；M0 測試 175 → 178
- 無頭測試：`test_combat.gd` 30、`test_board_writer.gd` 22（加上 10／11 共 134 項）
- 12／13 審查 14 項全部修正（潰散清暫停、排序測試優先序、目標 owner 每秒同步、視距半徑跟天氣、寫檔週期、`second()`、射線、註解照實）；`chief show` 讀不到檔重試 4 次（Windows 改名先刪再搬）；測試 34＋27；D22 落單殘排留老闆拍板（建議維持）

## 2026-11-02（第二十六次）— 施工單 10 本機驗收通過；施工單 11 方塊人、編制樹、編制 AI（程式完成）
- 老闆本機 Windows 無頭測試 exit 0（console 版、`m0://` 路徑、Jolt 正常）→ 10 ✅
- `godot/scripts/core/rules.gd`（讀同一份 `m0/rules`，查表邏輯同 rules.py）、`world/sector_grid.gd`（BFS 上左右下）、`units/order.gd`、`soldier.gd`（膠囊＋方塊頭、戰車方塊車、倒地）、`platoon.gd`（三班九人、站位、戰力＝存活比例）、`formation_ai.gd`（逐函式移植）、`orbat.gd`（雙方部隊樹、連令拆排、每 tick 推進、連級聚合）
- 時間對應落地：中心到中心 20 m／30 s、機動力 0.5＝60 秒一格、進敵格停 30 秒、分區看實際位置（docs/10 §15）
- `Battle`：讀 `board_deployed_balanced.json`＋`enemy_script_v1.json`、尋路格從掩體烘焙、HUD 顯示雙方戰力、空白鍵偵錯命令
- `tests/harness.gd`（看門狗）、`tests/test_orbat.gd` 34 項全過；`m0/samples/board_deployed_balanced.json` 新增
- 11 審查 15 項全部修正（全殲滅連當機、側翼闖森林、連分區取序與 M0 相反、潰散不限一格、站位、快取、拒建壞兵種、§15 補齊）；測試 34 → 50

## 2026-11-02（第二十五次）— M1 拍板（ADR-0014）、施工單 10～15 建檔、10 程式完成
- 老闆「好了」＝D15～D21 全照建議 → `docs/adr/0014-m1-godot-stack.md`；決策紀錄第五輪 ✅
- 施工單 10～15 建檔（`docs/issues/10～15`），索引與執行順序更新
- `godot/`：project.godot（4.7.2、Compatibility、Jolt）、`addons/rts_kit`（MIT 複製）、`BoardIO`（m0:// 讀隔壁 m0）、`SectorMap`（20 m 分區、地形色、擁有方色調、據點旗、城鎮 6 掩體／森林 8 樹、格線、座標反查、易手改色）、`Battle` 場景（光、環境、RTSCameraRig 俯仰 60°、HUD）、`tools/make_scene.gd`、`tests/run_tests.gd` 26 項（沙盒無頭全過）、README
- 10 審查 10 項全部修正：測試看門狗（執行期錯誤 exit 2）、Windows 用 console 版 exe、重建地圖先 remove_child、常數改 *_MASK、floori、BOM 死碼、路徑與開檔防呆、補 6 項測試（32）、輸入驗證
- 心智圖 M1 節點更新；回寫 Artifact 資料庫

## 2026-11-02（第二十四次）— 老闆下令「進入 M1」：T1.0 重用檢查與選型（Stage 2）
- 沙盒實測：Godot 4.7.2 Linux 無頭版可下載、可跑自寫的探針測試（3D、Jolt、JSON、user:// 寫檔）；第三方專案的測試受權限不執行
- 重用檢查：godot-rts-kit（MIT、4.7、2,270 行、5 節點、無頭測試、效能基準）建議採用；rts_demo（2D、Compatibility、零素材）只參考；ccoyle95 排除；huginhelm 找不到；Kenney 等素材 M1 不需要
- `docs/11-m1-architecture.md`：D15～D21 建議答案、M1 架構（同一份規則表、1 回合＝30 秒、每 100 ms 寫 board.json）、Windows 環境精靈、施工單草案 10～15
- `docs/05-decisions.md` 第五輪待決策；`docs/07` 驗證狀態更新；路線圖 T1.0 ✅；心智圖 M1 節點展開；回寫 Artifact 資料庫

## 2026-11-02（第二十三次）— 施工單 09 平衡與截斷（老闆指示「先修平衡與截斷問題，開新施工單」）
- 規則 §2 v1.1：潰散單位往「沒有敵軍的本方分區」退，守軍潰散後分區易手（原本留在城裡當肉盾，城鎮打不下來）
- 敵方劇本三級 `enemy_v1_easy.json`／`enemy_script_v1.json`／`enemy_v1_hard.json`＋`--difficulty`；平衡基準局 `orders_v1_assault.json`（easy 勝、normal 勝、hard 敗）寫進 §14 並以測試鎖住
- 提示：每回合 user 訊息加分數、未奪目標、剩餘回合；系統提示加「據點分定勝負、攻城集中三排＋迫砲」、評估 ≤ 120 字、reason 可空
- Anthropic adapter：max_tokens 4096；截斷時併入精簡要求重試一次（兩次計費，attempts=2）
- 戰報卡提示「整場沒有奪取任何新據點」（離線）、進 aar.json 與參謀長摘要、討論第 1 回合快速回覆
- `docs/issues/09`、README、HANDOFF（--difficulty normal）、路線圖 T0.12；心智圖加 09 節點；回寫 Artifact 資料庫
- 09 審查 10 項全部修正：easy 劇本去掉 t8 連令（40 種子 40 勝）、潰散撤出的效果改寫為「不分攤火力」並以手算鎖住、潰散退路避敵格、`--enemy` 給了就優先、重試改看 stop_reason、提示措辭；測試 157 → 175
- 新增 `chief replay`（回放一場）、`samples/doctrine_fresh.md`、`--harness none`／`--ledger none`（PowerShell 吃掉空字串）
- 真機 A/B（老闆本機 Haiku 5.5）：學完五場的保守準則 3:8；空白準則 8:3（t1 三排＋迫砲攻 C3、t7 拿下）→ 09 結案，敗仗來自學到的風格，迴圈運作正常

## 2026-11-02（第二十二次）— M0 真機驗收完成（老闆本機）
- 雲端環境變數 `ANTHROPIC_API_KEY` 送不進 session（主 session 與子 session 都看不到）→ 改在老闆 Windows 本機跑；HANDOFF 改寫
- 五場 Haiku 5.5＋模擬總司令（v1 戰鬥模型、均衡範本、v1 敵方劇本）：推翻率 8.8% → 3.7% → 4.2% → 3.2% → 4.0%，下降 ✅；戰後中位數 47 秒、跳過 0%；五場約 US$0.04
- 回歸：現行準則 14.3%（基準 33.3%）、壞準則 0.0% 印退步（試水溫不動真準則）；Ollama qwen2.5:3b 一場打完 0 無回應
- 發現 6 項寫進 `docs/qa/m0-review.md`：五場全敗 3:8 平衡待調、Haiku max_tokens=2048 截斷、對齊判定過嚴、獨立 evals 基準戰例集不同、Ollama 弱基準、雲端金鑰
- 施工單 05／06／07／08 全部 ✅，路線圖 M0 驗收 ✅，心智圖 M0 節點改 ✅；回寫 Artifact 資料庫

## 2026-11-02（第二十一次）— 施工單 08 戰鬥模型 v1（程式完成）
- `m0/rules/ww2_1944.json`（七兵種 × 火力／裝甲／速度／視距／點數；地形 5、天氣 4、時段 2 修正；三範本）＋冷戰早／晚骨架；`chief/rules.py` schema 檢查與查表（人話錯誤）
- 戰情板合約 v0.2：`era`、`weather`、`time_of_day`、`Unit.cost`；0.1 檔自動升級、`armor` → `tank`；`compact()` 多三鍵仍 < 2K token（均衡 8 排約 450）
- `chief/sim.py` 改查表：混合火力、掩蔽上限 0.8、天氣／時段倍率、迫砲鄰格間接射擊、工兵固守加成與過河、戰車不進森林、機動力減半只在偶數回合動、偵察 2 格、視距表；敵方劇本 `weather_changes`／`time_changes` 寫 `weather` 事件
- `chief/deploy.py`＋`chief deploy`（範本／自選配比／`--suggest` 請參謀長挑、`--out` 存板）；`chief sim/play --template --units --weather --time --era`；標題列顯示世代與天氣
- 系統提示注入 `{rules}`（約 340 token）；`samples/enemy_script_v1.json`（戰車、迫砲、反戰車；t3 雨、t6 夜、t8 霧）
- 文件：`docs/10` v1（§2、§4 查表與四組手算、§8 天氣變化、§13 部署）、`docs/09` v0.2、施工單 08 勾選、路線圖 T0.11；測試 123 → 146（`tests/test_rules.py`、`tests/test_combat_v1.py`）
- 08 審查（code-reviewer 軸）12 項全部修正：壞 era／壞劇本天氣／`mixed` 葉節點以人話退回、`--era` 生效、潰散只退 1 格、工兵加成要守該格、過河以回合開始位置為準、`armor` 一律轉 `tank`、`{rules}` 保底、`equipment` 欄位、快速單位進敵格即停、提示補迫砲觀測條件、地圖標題帶天氣；測試 146 → 157
- 心智圖：戰鬥模型 v1 與施工單 08 節點改 🟡（審查已修；待金鑰 session 重跑 5 場）；回寫 Artifact 資料庫

## 2026-11-02（第二十次）— 模擬總司令、測試軸修正、交接檔
- `chief/commander.py`＋`samples/commander_steady.json`：規則驅動的模擬總司令（`chief play --commander`），五場驗收可全自動；fake 供應商有示範劇本（`--model fake/empty` 為空劇本）
- 測試軸審查 14 項修正（期望值來源、公開介面、補 5 個測試）；測試 114 → 119；`docs/qa/m0-review.md` 三軸齊
- `HANDOFF.md`：金鑰確認、五場自動驗收、回歸、雙供應商、下一步 08
- 老闆問為何不能由 Claude 直接跑：雲端無 Ollama、無金鑰（設計如此）、Remote Control 不支援 Windows；解法 A＝金鑰加進雲端環境設定後由新 session 跑，B＝本機 Claude Code

## 2026-11-02（第十九次）— 07 審查修正、三審報告（PRD 軸、標準軸）
- 07 審查 9 項全部修正：包內路徑強制、暫存夾驗證、rename 正則、匯出排除、zip 上限、戰例 id 用資料夾名、每場獨立輸出夾、試水溫不回滾、compare 無法判定保護、基準記模型與先建基準、戰例回歸後才寫入
- PRD 符合度：推翻率唯一定義、S1／S2 補記、文件落後修正；`docs/qa/m0-review.md` 建立
- `run_play` 的 input 改執行時綁定（可替換）；測試 107 → 113

## 2026-11-02（第十八次）— 07 參謀長包＋戰例庫回歸＋驗收曲線
- `harness.py`（manifest 驗證、export zip 不含金鑰、import 路徑安全、rename/overwrite）、`evals.py`（戰例＝推翻當下快照＋原令＋改令；回歸＝重問對齊率；退步 > 5 點）、`acceptance.py`（stats 曲線、連打 N 場）
- `play.py`：每場推翻自動進戰例庫；採納後自動回歸，退步自動回滾；`--harness` 載入包（準則＋提示模板）
- CLI：`chief harness list|export|import`、`chief evals build|run [--doctrine 壞準則] [--rollback]`、`chief stats`、`chief acceptance --battles N`
- 規則 §12；`samples/bad_doctrine.md`；測試 99 → 106；三審（code-reviewer／test-automator／PRD 符合度）啟動

## 2026-11-01（第十七次）— 06 審查修正
- 審查員 9 項：準則刪除改「整行相同或 ≥8 字子字串、每條最多刪一行」（原本 "e" 會清空整份）、戰後 LLM 呼叫全部計費（phase=aar）並進帳本、2,000 字上限改為硬保證且剛新增的不淘汰、英文兩句截斷修正（小數、縮寫、空白）、手改準則的標題辨識與未知段落保留、自動模式不呼叫 LLM、討論數字越界重問、開局引用不含日期、標題 escape、aar.json 含完整卡
- 文件：03 徽章與 AAR 模型說明對齊程式；§11 補規則；README 加指令速查；測試 95 → 99

## 2026-11-01（第十六次）— 06 戰報卡＋討論＋採納準則
- 閘道通用化：`parse(messages, model)` 與 `chat(messages)`（LiteLLM／Anthropic／Fake 三者），`issue_orders` 改為其上的薄層
- `badges.py`（四種離線徽章）、`report.py`（戰報卡、關鍵三幕、參謀長一句話）、`discussion.py`（三回合、快速回覆、兩句截斷）、`doctrine.py`（DoctrineDiff、套用、上限淘汰、undo、開局引用、aar.json）
- `play.py` 戰後流程：卡 → 一句話 → 討論 → diff 提案 → 一鍵採納；`--skip-aar`、`--aar-provider/--aar-model`（anthropic 預設 Sonnet 5.5 做檢討）；`chief doctrine show|undo`
- 規則 §11 徽章與戰報卡；測試 86 → 95

## 2026-11-01（第十五次）— 05 審查修正；第四輪拍板 D11～D14
- 05 審查員 10 項：Ctrl+C／Ctrl+D 視同結束、玩家輸入不當 Rich 標記、接管連含所有下級（放手亦同）、玩家連令可拆給直轄排（Order 加 issuer）、編號固定不位移、開局快照 t0.json、推翻率分母不計提前結束回合、浮點邊界、未判定計數；測試 82 → 86
- 老闆提出兵種配比、二戰～冷戰科技、天氣地形 → D11～D14 全照建議 → ADR-0013；PRD v0.4 加 F15 部署配比、F16 世代與天氣；施工單 08 戰鬥模型 v1（在 07 之後、M1 之前）；目前戰鬥模型標為替身
- 同步工具：連結只認檔案路徑或網址，節點文字裡的 → 不再被誤當連結
- 心智圖：戰鬥沙盤加戰鬥模型 v1 子樹；回寫 Artifact 資料庫

## 2026-11-01（第十四次）— 05 總司令推翻與接管
- `chief/override.py`：推翻紀錄（overrides.jsonl）、後果判定（§9，t+1 回合結束判 👍👎➖）、玩家命令檢查
- `play.py` 互動模式（不加 `--auto`）：參謀長提案表 → Enter 採納／數字改令並接管／+ 接管／- 放手／q 結束；直轄單位任務延續、參謀長不得下令；戰後印推翻率與後果統計
- 以 Rich 提示迴圈取代原計畫的 Textual（M0 回合制更簡單可測；Textual 留 M2）
- 測試 75 → 82 全綠

## 2026-11-01（第十三次）— 03／04 真機驗收通過
- 老闆真機：Ollama 無回應 7→0 回合、token 59K→17K；Anthropic Haiku 5.5 一場 $0.0051、無回應 0。兩場皆 3:8 敗（敵方劇本含裝甲排，參謀長策略保守，交給 06/07 成長迴圈）
- 取消 V7：改為「排的明確命令優先於連令」（引擎語義，不再退回）；戰後印退回摘要與無回應原因；Anthropic 加 `--effort`
- 測試 75 全綠；開始 05

## 2026-11-01（第十二次）— 03 審查修正
- 審查員 16 項：連線被拒誤報成壞 JSON（改挖 `__cause__`）、無 timeout（預設 120 秒）、Rich 標記注入（模型字串一律 `Text()`）、連與排同回合互相覆蓋（新增 V7）、cache_write 未計、粗估法與戰情板不一致、instructor 噪音、準則路徑錯靜默；Ollama 改 json_schema 強制模式三段降級；provider.json 與架構文件、規則 §10 對齊
- 測試 67 → 74 全綠

## 2026-11-01（第十一次）— 03 真機首跑後的容錯、04 完成
- 老闆真機（Ollama qwen2.5:3b）首跑：10 回合、計量、快照皆正常，但 7 回合無合法 JSON → 用假回應重現四種失敗（圍欄、評估太長、同義詞、超過 5 條）全部被嚴格 schema 打回
- 修正：`orders.py` 改「寬進嚴出」（截斷、同義詞、大小寫正規化）；閘道改 instructor MD_JSON（容忍圍欄）＋ Ollama JSON 強制模式（不支援自動退回）；`play.py` 寫 `llm_log.jsonl` 留原始回覆、解析失敗回饋下一回合；提示明列可下令單位
- 04：`gateway/anthropic_adapter.py`（`messages.parse` 結構化輸出、系統提示快取、錯誤翻人話、refusal／max_tokens 處理）、`prices.json`、跨場帳本 `Ledger`、`--budget`（80% 提醒、100% 暫停）、HUD 本場／今天／本月、`.env` 自動載入
- 測試 57 → 67 全綠

## 2026-11-01（第十次）— 02 審查修正、03 程式完成
- 02 審查員回報 22 項（引擎不檢查目標會寫壞快照、潰散來回踱步、engaged 不復原、連令蓋直轄排、潰散永不受損等）全部修正；規則文件升 v0.2 補齊實作備註；補 11 個手算測試；移除誤入 repo 的暫存快照
- 03：`orders.py`（輸出合約）、`validator.py`（V1～V6）、`meter.py`（計量＋LiteLLM 內建價格表）、`prompts.py`＋`prompts/chief_system.md`、`gateway/`（介面、Fake、LiteLLM＋instructor JSON 模式）、`play.py`（自動指揮迴圈，退回回饋進下一回合）、`harness/default/doctrine.md`、`provider.json`；`chief play --provider ollama --auto`
- 測試 33 → 57 全綠；03 審查中；待老闆真機 Ollama 驗收

## 2026-11-01（第九次）— 施工單 01、02 完成
- 01 戰情板合約：`chief/board.py`、`render.py`、`cli.py`、`samples/board_t0.json`、`docs/09-board-schema.md`；審查員回報 21 項（含範例敵方少一排、任務目標檢查過寬、懸空 parent、版本不檢查、Windows 字元）全部修正，測試 10 → 20
- 02 模擬會戰：`chief/grid.py`、`formation_ai.py`、`sim.py`、`samples/board_start.json`、`orders_scripted.json`、`enemy_script.json`、`docs/10-sim-rules.md`（手算範例為測試期望值）；`chief sim` 子命令；測試 13 個；共 33 個全綠
- 心智圖 M0 節點更新；回寫 Artifact 資料庫

## 2026-11-01（第八次）— 進入 Stage 3，拆施工單
- 開工前檢查：未決決策 2 個（模擬規則粒度、推翻介面）附建議答案；預估檔案 ≥ 10 → 拆 7 張曳光彈施工單 `docs/issues/01～07`
- 心智圖 M0 節點展開為 7 張施工單；回寫 Artifact 資料庫

## 2026-11-01（第七次）— 環境建置精靈完成
- 老闆決定護欄不擋 git push；Windows 環境 7 步全部完成（uv、Git clone 到 C:\dev、Ollama qwen2.5:3b、Anthropic 金鑰、捕捉腳本寫入 .env、uv sync、doctor 全部通過）
- `docs/08` 進度表更新、心智圖 Stage 2 節點改 ✅；回寫 Artifact 資料庫

## 2026-11-01（第六次）— 進入 Stage 2
- 選型比價（WebSearch 降級＋沙盒 uv 實測）：uv、Textual 8.2.8、LiteLLM 1.106.6＋instructor 1.17.0、anthropic 2.3.0 → ADR-0012；`docs/08-stage2-architecture.md`
- M0 環境骨架 `m0/`：pyproject、uv.lock、.env.example、.gitignore、金鑰捕捉腳本（sh／ps1）、`chief/doctor.py` 體檢（已煙霧測試）
- 實體護欄：`ai-commander-game/.claude/hooks/block-dangerous.js`（隨專案搬家）＋ repo 根目錄 `.claude/settings.json` 指向它；自測 7 條全部符合預期
- `THIRD_PARTY.md` 建立（M0 部分）；心智圖加 M0 技術棧與 Stage 2 進度；回寫 Artifact 資料庫

## 2026-11-01（第五次）— 老闆指示「重用優先」
- ADR-0011 重用優先；新增 `docs/07-reuse-catalog.md`（RTS 骨架、布娃娃、地形、UI、方塊人素材、milsymbol、Textual、LiteLLM、instructor、TextStarCraft II 摘要鏈），全部標 ⚠️ 待 Stage 2 驗證
- 架構文件標註重用元件；路線圖加 T0.0、T1.0 重用檢查
- 心智圖新增「8. 素材與模板庫」，文件索引改為 9；回寫 Artifact 資料庫

## 2026-11-01（第四次）— 老闆第三輪「全照建議」，D1～D10 全部定案
- D1 Godot 4 → ADR-0001；D8 規模階梯 → ADR-0008；D9 Anthropic＋Ollama → ADR-0009
- `05-decisions.md` 狀態改 ✅；`03-architecture.md`、`04-roadmap.md`、`06-engine-comparison.md`、README 標題同步
- 心智圖：D1／D8／D9 節點改 ✅，新增「待老闆下令進入 Stage 2」；回寫 Artifact 資料庫

## 2026-11-01（第三次）— 老闆第二輪：D10 拍板＋兩項新需求
- D10 否決建議：對決不設限制，寫 `docs/adr/0010-duels-unrestricted.md`
- 新需求 F13 Token 與費用計量、F14 戰報卡＋討論（遊戲化從簡）→ `02-prd.md` v0.3、`03-architecture.md` v0.3、`04-roadmap.md`（T0.9、T0.10、T2.7、T2.8）
- 心智圖：核心玩法加「戰報卡＋討論」子樹；技術架構加「Token 計量」子樹；D10 改 ✅；回寫 Artifact 資料庫

## 2026-11-01（第二次）— 老闆第一輪拍板，設計改版 v0.2
- 拍板：D2、D3、D4、D5、D6、D7 → 寫入 `docs/05-decisions.md` 拍板紀錄與 `docs/adr/0002～0007`
- 設計改版：AI 全盤操作、玩家隨時推翻；常駐 AI 戰情板；多供應商 LLM 閘道；參謀長包與對決；三語 → `02-prd.md`、`03-architecture.md`、`04-roadmap.md` 全部改到 v0.2
- 新增 `06-engine-comparison.md`（D1 用）；新增第二輪決策 D8～D10
- 心智圖改成互動 Artifact：https://claude.ai/artifact/YRdMT6jZYGpmQfKvc7feib （資料存 Artifact 資料庫 `mindmap/main`，已寫入 version 1）；`tools/sync_mindmap.py` 加 JSON 匯入／匯出，`MINDMAP.md` 為鏡像；頁面原始碼 `mindmap-editor.html`
- 心智圖節點重排：新增「3. AI 戰情板」，技術架構加閘道與參謀長包

## 2026-11-01（第一次）— 專案啟動（Stage 1）
- 建立心智圖 `MINDMAP.md` 與產生器 `tools/sync_mindmap.py`，輸出 `mindmap.html`
- 新增 `docs/01-feasibility.md`、`02-prd.md`、`03-architecture.md`、`04-roadmap.md`、`05-decisions.md`
