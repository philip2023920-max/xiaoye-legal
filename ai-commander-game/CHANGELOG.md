# 變更紀錄（心智圖與文件同步日誌）

每次依心智圖施工後，在此新增一條：日期｜動了哪些節點｜改了哪些檔案。

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
