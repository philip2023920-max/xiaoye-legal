---
title: AI 參謀長 RTS 心智圖
markmap:
  colorFreezeLevel: 2
  initialExpandLevel: 2
  maxWidth: 360
---

# AI 參謀長 RTS（代號 CHIEF）

## 0. 這張圖怎麼用 📖
- 狀態符號：⬜ 未開始｜🟡 進行中｜✅ 完成｜❌ 作廢｜❓ 待老闆決策
- **老闆改法**：直接編輯 `MINDMAP.md`（加節點、改狀態、寫備註），存檔
- **Claude 施工法**：讀本圖 → 只做標 🟡 的節點 → 完成改 ✅ → 執行 `python tools/sync_mindmap.py` → 寫 `CHANGELOG.md`
- 節點後的 `→ docs/...` 是對應說明書；改決策請改 `docs/05-decisions.md`
- 階段切換要老闆明說（「進入 Stage 2」）；Claude 不自己往下跳
- 完整規則 → README.md

## 1. 願景與定位 🎯
- 一句話：玩家是總司令，AI 是會越打越懂你的參謀長 ✅ → docs/02-prd.md
- 核心賣點：成長迴圈，不是畫面 ✅ → docs/01-feasibility.md
- 參考：Company of Heroes 3（指揮感）＋ TABS（畫面風格）
- 同業：Pax Historia（LLM 顧問＋指令驗證器）✅ 已查證
- 差異化：跨戰役成長的參謀長，目前無成品 ✅ 已查證
- 可行性判定：✅ 高（技術無需突破；體驗需 M0 實測）

## 2. 核心玩法：參謀長成長迴圈 🔁 → docs/03-architecture.md
- 觀察 Observe：遊戲狀態 → 壓縮快照 JSON（< 2K token）⬜
- 提案 Propose：Claude 以 strict tool `propose_orders` 提 1～3 條建議 ⬜
- 裁決 Decide：玩家採納／否決／修改 ⬜
- 執行 Act：指令驗證器把關，不合法退回 ⬜
- 結果 Outcome：勝負、損失、時間線寫入 battle log ⬜
- 反思 Reflect：AAR 檢討官更新 Doctrine（有字數上限）⬜
- 評估 Evaluate：戰例庫回歸測試，退步就回滾 ⬜
- 作戰準則 Doctrine 格式
  - 總司令風格畫像
  - 已驗證戰術（採納率 > 70%、≥ 3 場）
  - 被否決的做法
  - 待驗證假設
- 成功定義：第 5 場採納率 > 70%；首字延遲 < 2 秒 → docs/02-prd.md

## 3. 戰鬥沙盤（畫面簡化）🎮 → docs/02-prd.md
- 風格：TABS 低多邊形、無貼圖、單色材質、固定俯視
- 單位：膠囊體＋方塊頭，3 種（步兵／機槍／裝甲）⬜
- 物理：走路簡單搖晃；死亡才切 ragdoll ⬜
- 地圖：1 平面＋3 據點＋方塊掩體 ⬜
- 敵方：固定劇本 AI ⬜
- 效能目標：200 單位 60 FPS，2018 內顯筆電 ⬜
- 本版不做：多人、資源採集、基地建造、語音、AI 自動接管

## 4. 技術架構 🧱 → docs/03-architecture.md
- 引擎：Godot 4（建議，待 D1 拍板）❓
  - Plan B：Three.js + Rapier
- LLM 層
  - 節拍模型 claude-haiku-5-5；AAR 模型 claude-sonnet-5-5 ❓ D3
  - strict tool + tool_choice auto（新模型不支援強制 any/tool）
  - prompt caching：系統提示＋Doctrine 在前，快照在後
  - 串流 streaming
  - ⚠️ Godot LLM Framework addon 需老闆實測；備案 HTTPRequest 直呼
- 資料層：doctrine.md、profile.json、battles/*.jsonl、evals/
- 金鑰：MVP BYOK 存 user://，不進 repo 不進對話 ❓ D4
- 成本：每場約 US$0.1 ✅ 已估算

## 5. 里程碑 🗓️ → docs/04-roadmap.md
- M0 文字版沙盤（2 週）⬜ ← 建議第一步 ❓ D2
  - sandbox.py 回合制小戰局
  - 參謀長呼叫 + 終端機裁決
  - AAR + Doctrine diff
  - 戰例庫回歸
  - 驗收：5 場採納率上升
- M1 Godot 戰鬥沙盤（4～6 週）⬜
- M2 參謀長接入 Godot（4 週）⬜
- M3 可玩 Demo + itch.io（2～3 週）⬜
- M4 商業化（不排程）❌ 本版不做

## 6. 風險與待決策 ⚠️ → docs/05-decisions.md
- 風險
  - LLM 延遲 → 決策節拍＋串流 ✅ 有解法
  - 幻覺指令 → schema 合約＋驗證器 ✅ 有解法
  - 「變強」變垃圾堆 → Doctrine 上限＋戰例庫回歸 ✅ 有解法
  - 體驗是否夠爽 → 只能靠 M0 實測 ❓
- 待老闆拍板（可整批回「全照建議」）
  - D1 引擎 Godot 4 ❓
  - D2 先做 M0 文字版 ❓
  - D3 模型 Haiku 節拍／Sonnet AAR ❓
  - D4 金鑰 BYOK ❓
  - D5 即時＋決策節拍 ❓
  - D6 開新 repo ❓
  - D7 介面繁中、Doctrine 雙語 ❓

## 7. 文件索引 📂
- README.md（規則與工作流程）
- docs/01-feasibility.md（可行性＋來源）
- docs/02-prd.md（PRD＋商業評分 6/10）
- docs/03-architecture.md（架構＋資料格式）
- docs/04-roadmap.md（M0～M4）
- docs/05-decisions.md（D1～D7）
- docs/adr/（拍板後的決策備忘卡，目前空）
- CHANGELOG.md（每次同步紀錄）
