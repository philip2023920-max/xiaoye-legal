---
title: AI 參謀長 RTS 心智圖
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 2
  maxWidth: 360
---

# AI 參謀長 RTS（代號 CHIEF）

## 0. 這張圖怎麼用 📖
- 備註寫法：以 💬 開頭的子節點是備註（老闆寫給 Claude 的話，或 Claude 的回覆）
- 狀態符號：⬜ 未開始｜🟡 進行中（叫 Claude 做）｜✅ 完成｜❌ 作廢｜❓ 待老闆決策
- 老闆改法 A：在互動心智圖 Artifact 裡直接改（加節點、改狀態、寫備註）；改完告訴 Claude「照心智圖做」
- 老闆改法 B：直接編輯 `MINDMAP.md`；兩邊衝突時以 Artifact 為準
- Claude 施工法：讀 Artifact 資料庫 → 轉回 MINDMAP.md → 只做 🟡 節點與老闆備註 → 改 ✅ → 回寫 Artifact → 寫 CHANGELOG.md
- 重用優先（ADR-0011）：每張施工單先找現成素材／模板／套件，能用就用、能改就改，最後才自製
- 階段切換要老闆明說（「進入 Stage 2」）；Claude 不自己往下跳
- 目前階段：Stage 3 程式碼實作 🟡 → docs/issues/README.md
- 完整規則 → README.md

## 1. 願景與定位 🎯
- 一句話：AI 參謀長全盤指揮，玩家是總司令，隨時可推翻；每次推翻都在訓練它 ✅ → docs/02-prd.md
- 核心賣點：成長迴圈與參謀長生態，不是畫面 ✅ → docs/01-feasibility.md
- 參考：Company of Heroes 3（指揮感）＋ TABS（畫面風格）
- 聚焦：物理世界中的會戰，不做大戰略（ADR-0005） ✅
- 同業：Pax Historia（LLM 顧問＋指令驗證器），已查證 ✅
- 差異化：會成長、可打包、可對決的參謀長，目前無成品 ✅
- 可行性判定：高（技術無需突破；體驗需 M0 實測） ✅

## 2. 核心玩法：指揮、推翻、成長 🔁 → docs/03-architecture.md
- AI 自動指揮：每個決策節拍對編制層級下任務式命令（M0 文字版完成） ✅
- 指揮鏈：LLM 管意圖（軍團旅連），編制 AI 管執行（排班） ⬜
- 玩家推翻與接管：任一級隨時接管，放手後 AI 接回（M0 文字版：數字改令、+ 接管、- 放手） ✅
- 推翻紀錄：AI 原令、玩家改令、當時快照、後果 👍👎➖（overrides.jsonl） ✅
- 指令驗證器：不合法的令退回並記錄（V1～V6） ✅
- 戰後檢討 AAR：推翻在哪、轉折、學到什麼；可一鍵撤銷（chief doctrine undo） ✅
- 作戰準則 Doctrine（有結構、有上限 2,000 字；超限先淘汰假設） ✅
  - 總司令風格畫像
  - 已驗證戰術
  - 被推翻的做法
  - 待驗證假設
- 戰例庫回歸：採納後自動重跑戰例，對齊率退步 > 5 點就回滾 ✅
- 戰報卡＋討論（遊戲化、從簡：一張卡、三幕、三回合、一個按鈕） ⬜
  - 戰報卡：戰果、推翻次數、花費、徽章；程式產生不花 token ✅
  - 關鍵三幕：玩家 vs AI 決策對照＋後果 👍👎 ✅
  - 討論：最多三回合，快速回覆選項，AI 回覆限兩句 ✅
  - 採納畫面：準則 diff 一鍵採納／不採納；下一場開局引用 ✅
  - 徽章：果斷總司令、放手型、省錢贏家、本地派、守土有責（離線判定）✅；信任計量條留 M2 ⬜
- 成功定義：第 5 場推翻率 < 15%；命令首字 < 2 秒；戰後流程 < 2 分鐘 → docs/02-prd.md

## 3. AI 戰情板（常駐沙盤）🗺️ → docs/03-architecture.md
- 原則：人與 AI 看同一份；設計給 AI 讀，玩家側欄即時顯示（ADR-0002） ✅
- 內容：分區地圖、部隊樹（班排連旅軍團）、事件流、目標、戰爭迷霧 ⬜
- 更新：引擎每 100 ms 寫入；LLM 在節拍讀壓縮版（< 2K token） ⬜
- 玩家直轄標記：接管中的部隊在板上標示，AI 不再對它下令（V2） ✅
- M0 就要定好資料格式（所有層的共用合約） ✅ → docs/09-board-schema.md
  - 💬 Claude：這是 M0 的第一張施工單

## 4. 戰鬥沙盤（畫面簡化）🎮 → docs/02-prd.md
- 風格：TABS 低多邊形、無貼圖、單色材質、固定俯視
- 規模階梯（ADR-0008） ✅ → docs/05-decisions.md
  - 遭遇戰：班排，每人一個方塊人，死亡 ragdoll
  - 會戰：連旅，一班一組三個方塊人
  - 大會戰：旅軍團，棋子，拉近才展開
- 單位：膠囊體＋方塊頭；兵種七種（步兵、機槍、迫砲、反戰車、戰車、偵察、工兵） ⬜
- 地圖：平面＋據點＋方塊掩體 ⬜
- 敵方：固定劇本 AI（對決模式時換成另一個參謀長） ⬜
- 效能目標：會戰規模 60 FPS，2018 內顯筆電 ⬜
- 戰鬥模型 v1（ADR-0013，資料表驅動；程式完成，審查 12 項已修；待 5 場真機重跑） 🟡 → docs/10-sim-rules.md
  - 兵種七種 × 屬性；點數預算部署配比＋三種範本（D11）
  - 科技世代：二戰 1944 先做；早期／晚期冷戰預留表格（D12）
  - 天氣四種 × 日夜：影響視距、移動、掩蔽、裝甲通行；一場中可變（D13）
  - 場內砲兵（迫砲、砲兵連）；空中支援留 M3（D14）
  - 數字全在 m0/rules/ww2_1944.json，老闆可直接改；舊的 3 兵種替身公式已作廢
- 本版不做：多人、資源採集、基地建造、語音、純建議模式、空中支援

## 5. 技術架構 🧱 → docs/03-architecture.md
- 引擎：Godot 4（ADR-0001；M0 用 Python 不綁引擎） ✅ → docs/06-engine-comparison.md
  - Godot 4：免費、輕、GDScript 好學；4.4+ 內建 Jolt 物理
  - Unity 6（若日後要上主機再考慮） ❌
  - 純網頁 Three.js（Plan B／展示版）
  - Unreal 5、Bevy：排除 ❌
- LLM 閘道（多供應商，ADR-0003） ✅
  - Anthropic 原生 adapter：messages.parse 結構化輸出＋prompt caching（串流延後 M2） ✅
  - OpenAI 相容 adapter：LiteLLM＋instructor JSON 模式（Ollama 先驗，其餘同路徑） ✅
  - 最低公分母：schema 進提示 → JSON → 本地驗證 → 重試 ≤ 2 ✅
  - 供應商能力表 provider.json ✅
  - 首批：Anthropic 原生＋Ollama 本地（ADR-0009） ✅
- 參謀長包 Harness：manifest、doctrine、prompts、evals 打包 ✅
  - 匯出／匯入（zip，不含金鑰，路徑安全檢查） ✅
  - 參謀長對決：兩個包各指揮一方，本地對戰 ⬜
  - 官方挑戰包（GitHub Releases） ⬜
  - 對決不設限制，任何包搭任何模型；畫面並列雙方模型與花費（ADR-0010） ✅
- Token 計量與費用估算 ⬜ → docs/03-architecture.md
  - UsageMeter 記錄每次呼叫的輸入／輸出／快取 token ✅
  - 價格表：LiteLLM 內建表＋prices.json 覆寫（附更新日期） ✅
  - HUD：本場／今天／本月（ledger.jsonl）；預算 80% 提醒、100% 暫停 ✅
  - 本地模型顯示 $0 但仍顯示 token 與秒數 ✅
- M0 技術棧（ADR-0012，沙盒實測安裝通過） ✅ → docs/08-stage2-architecture.md
  - uv 管 Python 與套件；版本鎖在 m0/uv.lock
  - Textual 8.2.8 終端機戰情板
  - LiteLLM 1.106.6＋instructor 1.17.0：OpenAI 相容路徑與價格表
  - anthropic SDK 2.3.0：原生路徑（strict tool、parse、快取、串流）
  - pydantic、pytest、python-dotenv
- 資料層：harness/、battles/*.jsonl、evals/
- 金鑰：BYOK 存本機加密設定，不進 repo 不進對話（ADR-0004） ✅
- 三語：繁中／簡中／英文，字串抽資源檔（ADR-0007） ✅
- 成本：Haiku 等級每場約 US$0.1；本地模型 0 ✅

## 6. 里程碑 🗓️ → docs/04-roadmap.md
- M0 戰情板＋文字版沙盤（Python，2～3 週；ADR-0002） 🟡 → docs/issues/README.md
  - 施工單 01 戰情板合約＋靜態渲染（審查 21 項已修，20 測試） ✅ → docs/09-board-schema.md
  - 施工單 02 模擬會戰可跑（無 LLM）（審查 22 項已修，24 測試） ✅ → docs/10-sim-rules.md
  - 施工單 03 參謀長下令：Ollama 路徑（真機驗收：無回應 7→0，審查 16 項已修） ✅
  - 施工單 04 Anthropic 路徑＋費用計量（真機驗收：Haiku 一場 $0.005） ✅
  - 施工單 05 總司令推翻與接管（審查 10 項已修，11 測試；待真機驗收） 🟡
  - 施工單 06 戰報卡＋討論＋採納（審查 9 項已修，12 測試；待真機驗收） 🟡
  - 施工單 07 參謀長包＋戰例庫回歸＋5 場驗收（審查已修；三審報告 docs/qa/m0-review.md；待老闆 5 場真機驗收） 🟡
  - 施工單 08 戰鬥模型 v1：兵種、世代、天氣、部署配比（資料表、部署、查表解算、天氣變化、新劇本；審查 12 項已修；157 測試；待 5 場真機重跑） 🟡 → docs/issues/08-combat-model-v1.md
  - 執行順序：01、02、03、（04∥05 並行）、06、07、08，然後 M1
  - 戰情板資料格式與側欄文字渲染
  - 模擬會戰（連級，10 回合）
  - LLM 閘道：Anthropic 原生＋Ollama 本地
  - 命令合約 issue_orders＋驗證器
  - 終端機推翻介面
  - AAR＋Doctrine diff＋戰例庫回歸
  - Token 計量與每場費用小結
  - 戰報卡文字版＋討論三回合＋採納 diff
  - 驗收：5 場推翻率下降；回歸能抓到壞準則
  - Stage 2 環境建置（Windows，體檢全部通過） ✅
    - 環境骨架 m0/（pyproject、uv.lock、.env.example、doctor） ✅
    - 金鑰捕捉腳本 macOS／Windows（金鑰不進聊天） ✅
    - 實體護欄 .claude/hooks 已裝並自測 ✅
    - 環境建置精靈 7/7：uv、Git、Ollama qwen2.5:3b、金鑰、.env、doctor ✅
    - THIRD_PARTY.md（M0 部分） ✅
- M1 Godot 4 戰鬥沙盤（4～6 週） ⬜
- M2 參謀長接入＋玩家接管 UI（4 週） ⬜
- M3 可玩 Demo＋參謀長包＋對決＋itch.io（3～4 週） ⬜
- M4 商業化（不排程，本版不做） ❌

## 7. 風險與待決策 ⚠️ → docs/05-decisions.md
- 風險
  - LLM 延遲 → 決策節拍＋串流＋任務式命令，有解法 ✅
  - 幻覺指令 → schema 合約＋驗證器，有解法 ✅
  - 「變強」變垃圾堆 → Doctrine 上限＋戰例庫回歸，有解法 ✅
  - 軍團規模 vs 低硬體 → 規模階梯（ADR-0008） ✅
  - 便宜或本地模型常被退回 → 能力表＋驗證器重試，M0 用 Ollama 先驗 ✅
  - 體驗是否夠爽 → 只能靠 M0 實測 ❓
- 第一輪已拍板：D2 M0 戰情板、D3 多供應商、D4 BYOK、D5 AI 主控可推翻、D6 新 repo、D7 三語 ✅
- 第二輪已拍板：D10 對決不設限制；新需求 Token 計量（F13）、戰報卡＋討論（F14） ✅
- 第三輪已拍板（全照建議）：D1 Godot 4、D8 規模階梯、D9 Anthropic＋Ollama ✅
- 第四輪已拍板（全照建議）：D11 兵種配比、D12 世代、D13 天氣時段、D14 砲兵（ADR-0013） ✅
- Stage 2 已啟動 ✅
- 護欄不擋 git push（老闆決定） ✅
- 環境建置精靈完成，老闆電腦 doctor 全部通過 ✅
- Stage 3 已啟動；M0 拆成 7 張曳光彈施工單，等老闆點頭後動工 ❓ → docs/issues/README.md

## 8. 素材與模板庫 🧰 → docs/07-reuse-catalog.md
- 原則：先找、再改、最後才自製；授權 CC0 ＞ MIT ＞ CC-BY ＞ 其他（ADR-0011） ✅
- 進專案的東西記在 THIRD_PARTY.md ⬜
- Godot 戰鬥沙盤
  - RTS 骨架：godot-rts-kit（MIT）或 huginhelm Lite（MIT），M1 擇一 ⬜
  - 編隊參考：rainwindskyfly/rts_demo（MIT） ⬜
  - 布娃娃：Active Ragdoll（MIT）、Drop-In Ragdoll、Auto Ragdoll ⬜
  - 地形：Low Poly Terrain Builder；大會戰才看 Terrain3D（MIT） ⬜
  - UI 主題：Kenney UI Theme、Minimalistic UI、Crisp Kit ⬜
- 美術
  - 方塊人：Kenney Blocky Characters（CC0）＋Character Assets 動畫 ⬜
  - 環境／載具：Quaternius（⚠️ 新授權 QAL 逐包看）、Kenney Prototype、Poly Pizza CC0 篩選 ⬜
  - 軍事符號：milsymbol（MIT）預渲染 SVG ⬜
  - 音效：Kenney Audio、freesound CC0 ⬜
- Python M0
  - 終端機戰情板：Textual（MIT） ⬜
  - 閘道：LiteLLM（MIT）＋價格表 json；結構化輸出：instructor（MIT） ⬜
  - 提示方法：TextStarCraft II 的摘要鏈（只借方法） ⬜
- 驗證狀態：全部 ⚠️ 待 Stage 2 逐項驗證授權與版本

## 9. 文件索引 📂
- README.md（規則與工作流程）
- docs/01-feasibility.md（可行性＋來源）
- docs/02-prd.md（PRD v0.2）
- docs/03-architecture.md（架構 v0.2）
- docs/04-roadmap.md（M0～M4）
- docs/05-decisions.md（拍板紀錄＋第二輪）
- docs/06-engine-comparison.md（引擎比較）
- docs/07-reuse-catalog.md（素材與模板目錄）
- docs/08-stage2-architecture.md（Stage 2 選型與環境建置）
- docs/issues/（M0 施工單 01～07）
- docs/09-board-schema.md（戰情板合約）
- docs/10-sim-rules.md（模擬會戰規則與手算範例）
- THIRD_PARTY.md（第三方元件與授權）
- m0/（M0 環境骨架）
- docs/adr/（ADR-0001～0013）
- CHANGELOG.md（每次同步紀錄）
