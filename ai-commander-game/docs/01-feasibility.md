# 01 可行性分析：AI 參謀長 RTS

> 文件狀態：✅ v0.1 初稿（2026-11-01）｜對應心智圖節點：`1. 願景與定位`、`6. 風險`
> 研究方式：deer-flow 未開機，改用 WebSearch 降級研究（研究深度受限，已附來源）。

## 一句話結論

**可以做，而且比「做一個 RTS」容易得多。** 真正的產品不是戰場畫面，而是「參謀長成長迴圈」。
畫面走 TABS 風格的方塊人＋低多邊形，技術上是入門等級；難點集中在三件事：
LLM 的**延遲**、**亂下指令（幻覺）**、以及「變強」要**量得出來**（否則只是 prompt 越堆越長）。
這三件事都有成熟解法，寫在下方。

## 老闆的點子，翻成工程語言

| 老闆的話 | 工程上的意思 | 業界對應概念 |
|---|---|---|
| 玩家是總司令、AI 是參謀長 | 玩家保留最終決策權，LLM 負責「觀察 → 提案 → 解釋」 | Human-in-the-loop agent |
| 參謀長每場戰役變強、適應玩家風格 | 戰後把「提案被採納/否決 + 戰果」回饋進一份會演進的「作戰準則」檔 | Memory + Reflection（自我反思） |
| 玩家無形中建立 harness 與 loop | 遊戲本身就是一個「評估 → 改進 → 再評估」的閉環，玩家行為就是訓練訊號 | Eval harness / hill-climbing |
| 畫面簡略、硬體需求低 | 低多邊形、無貼圖、固定視角、數十到數百單位 | TABS 風格 |

## 同業與參考案例（查證結果）

- **Pax Historia（Y Combinator W2026）**：目前查到最接近的已上市案例。遊戲內有「Ask」顧問，每回合把完整世界狀態送給模型，另有 **action validator（指令驗證器）** 與世界事件產生器，玩家可從 28+ 個模型中挑選（評論者認為選項太多反而嚇到玩家）。
  → 對老闆的啟示：(1) 這條路線有人在走，證明可行；(2) **指令驗證器是必備零件**，LLM 的提案要先過遊戲規則檢查；(3) 模型選擇要幫玩家做好，不要丟 28 個選項。
- **Anthropic Advisor Strategy（2026-04 公開）**：便宜的執行模型跑整段任務，只在難題時才請教 Opus 等高階模型。對我們的意義：**平時的戰術節拍用便宜模型，戰後檢討用高階模型**，成本可控。
- 目前**沒查到**「LLM 參謀長會跨戰役成長」的 RTS 成品。這是老闆點子的差異化所在，但也代表沒有現成教科書可抄，需要自己做小步驗證。

## 三大技術風險與解法

### 風險 1：RTS 是即時的，LLM 回覆要 2～10 秒
- **解法：決策節拍（Decision Tick）**。參謀長不是每一幀都講話，而是每 15～30 秒、或遇到事件（部隊被殲滅、發現敵軍）才出聲。
- 回覆用**串流（streaming）**，第一句話 1 秒內就出現；玩家不等它，遊戲照跑。
- 比喻：真實的參謀長也不會每秒報告，是「報告長官，左翼吃緊，建議調預備隊」。

### 風險 2：LLM 亂下指令（幻覺）
- **解法：schema 合約 + 遊戲端驗證器**。參謀長只能透過固定格式的「提案工具」說話（例如 `propose_orders`，欄位：單位 ID、動作、目標座標、理由），由遊戲程式驗證：單位存在嗎？座標在地圖內嗎？有這個能力嗎？不合法的提案直接退回並記錄。
- 這也是核心原則 6（結構化輸出）的落實：**合約 > 期待**。

### 風險 3：「變強」變成「prompt 垃圾堆」
- **解法：作戰準則（Doctrine）＋戰例庫（Eval Set）**。
  - 作戰準則是一份有結構的 Markdown：玩家風格畫像、已驗證的戰術規則、被否決的做法。每場戰後由「檢討官」模型用固定格式更新，有上限（例如 2,000 字），超過就要合併或淘汰。
  - 戰例庫是歷史戰局快照：每次更新準則後，拿舊戰局重新問參謀長，比較「提案採納率」與「模擬戰果」有沒有退步。退步就回滾。
  - 這就是老闆說的「harness 與 loop」，而且玩家完全不用懂這些詞。

## 引擎選型（降級研究結果，進 Stage 2 前仍需正式比價）

| 方案 | 優點 | 缺點 | 適合度 |
|---|---|---|---|
| **Godot 4**（MIT 免費） | 零授權費、低多邊形 3D 夠用、內建 HTTPRequest 可直接呼叫 Claude API、已有社群 addon「Godot LLM Framework」支援 Claude（⚠️ 需老闆實測狀態）、GDScript 像 Python 好學 | 3D 效能不及 Unity/Unreal；主機平台匯出要靠第三方 | ★★★★★ 首選 |
| Unity 6 | 教學多、資產商店大 | 訂閱授權、對新手較重、政策曾反覆 | ★★★ |
| 純網頁 Three.js + Rapier 物理 | 不用安裝、分享給朋友一個網址就能玩 | 編輯器工具少、物理與數百單位的效能要自己調 | ★★★（作為 Plan B） |

結論：**建議 Godot 4**，理由是免費、單人開發友善、低硬體需求路線相符。這是老闆的決策，列在 `05-decisions.md`。

## TABS 風格畫面的實作難度

- Godot 官方有 ragdoll（布娃娃）文件：用 `PhysicalBone3D`，編輯器可自動產生，建議刪掉手指等小骨頭以省效能。
- **但 KISS 版不做全身物理**：單位是「膠囊體＋方塊頭」的剛體，走路用簡單搖晃動畫，**死亡那一刻才切 ragdoll**。這樣 200 個單位在五年前的筆電上也能跑。
- 畫面無貼圖、單色材質、固定俯視攝影機，美術成本接近零。

## 成本估算（以 Claude 官方價為準，2026-10 價格表）

| 用途 | 模型 | 每場戰役估算 | 說明 |
|---|---|---|---|
| 戰術節拍（每 20 秒一次，一場約 30 次） | Haiku 5.5（$0.10 / $0.50 每百萬 token） | 約 90K 輸入 + 15K 輸出 ≈ **US$0.02** | 搭配 prompt caching 把準則快取，更便宜 |
| 戰後檢討（AAR） | Sonnet 5.5（$2 / $10） | 約 20K 輸入 + 4K 輸出 ≈ **US$0.08** | 需要判斷力，用中階模型 |
| 戰例庫回歸測試（每次準則更新） | Haiku 5.5 | 10 個戰例 ≈ **US$0.01** | 背景跑 |

→ **一場完整戰役約 US$0.1 上下**。玩家 BYOK（自帶 API 金鑰）時成本在玩家端；若未來商業化走代理伺服器，每月 1,000 場約 US$100，可用訂閱覆蓋。

## 硬體需求（目標）

- 任意 2018 年後的筆電、內顯即可；Godot 用 Compatibility（OpenGL）渲染器。
- 網路：需要連線呼叫 API（可設計離線模式：參謀長靜音，遊戲照玩）。

## 最終判定

| 項目 | 判定 |
|---|---|
| 技術可行性 | ✅ 高。所有零件都有現成技術，無需研究級突破 |
| 單人＋AI 協作開發 | ✅ 可行。先做「文字版沙盤」驗證迴圈，再長畫面 |
| 最大不確定性 | ❓ 「參謀長真的會越來越像我」這個體驗是否夠爽——這要靠 M1 原型實測，不是靠分析 |

## 來源

- Godot vs Unity 2026 綜合比較：https://tech-insider.org/godot-vs-unity-2026/ 、https://oceanviewgames.co.uk/blog/posts/unity-vs-godot-vs-unreal-2026 、https://ziva.sh/blogs/unity-vs-godot-2026-ai
- Godot 官方 ragdoll 文件：https://docs.godotengine.org/en/4.2/tutorials/physics/ragdoll_system.html
- Godot LLM Framework（Claude 支援）：https://godotengine.org/asset-library/asset/edit/13656 ；C3 OpenAI-compatible client：https://store.godotengine.org/asset/c3designs/c3-openai-compatible-client/ ；Godot 呼叫 ChatGPT 教學：https://gamedevacademy.org/godot-chatgpt-tutorial/
- Pax Historia（YC W2026）評論：https://www.startuphub.ai/ai-news/claudes-corner/2026/claudes-corner-pax-historia-yc-w2026
- Anthropic Advisor Strategy 解說：https://www.buildfastwithai.com/blogs/anthropic-advisor-strategy-claude-api 、https://mindwiredai.com/2026/04/13/claude-api-advisor-strategy-cost-reduction/
- markmap（Markdown 轉心智圖）：https://markmap.js.org/docs/packages--markmap-autoloader 、https://pypi.org/project/markmap-cli/
