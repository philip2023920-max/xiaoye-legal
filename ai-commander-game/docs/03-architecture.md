# 03 技術架構草案

> 文件狀態：🟡 v0.1 草稿（2026-11-01）｜對應心智圖節點：`4. 技術架構`
> ⚠️ 本文是 Stage 1 的「方向草案」。正式選型、deer-flow 比價、環境建置、ADR 要等老闆說「進入 Stage 2」才做。

## 系統分層（由下往上）

```
┌─────────────────────────────────────────────────┐
│ 4. 成長迴圈層（Harness）                          │
│    AAR 檢討官 → 更新 Doctrine → 戰例庫回歸 → 回滾 │
├─────────────────────────────────────────────────┤
│ 3. 參謀長層（LLM Agent）                          │
│    快照壓縮 → Claude API（strict tool）→ 驗證器   │
├─────────────────────────────────────────────────┤
│ 2. 戰鬥沙盤層（Godot 4）                          │
│    單位、地圖、簡化物理、決策節拍、建議卡片 UI     │
├─────────────────────────────────────────────────┤
│ 1. 資料層（本機檔案）                             │
│    doctrine.md、profile.json、battles/*.jsonl、evals/│
└─────────────────────────────────────────────────┘
```

比喻：第 2 層是戰場，第 3 層是站在你旁邊的參謀長，第 4 層是他晚上回去寫日記、反省、整理筆記的習慣，第 1 層是那本筆記本。

## 核心迴圈（這就是老闆說的 harness + loop）

```
觀察(Observe) → 提案(Propose) → 裁決(Decide) → 執行(Act) → 結果(Outcome)
      ↑                                                        ↓
      └──────── 更新準則(Reflect) ← 回歸測試(Evaluate) ←────────┘
```

| 步驟 | 誰做 | 輸入 | 輸出 |
|---|---|---|---|
| 觀察 | Godot | 遊戲狀態 | 壓縮後的戰局快照 JSON（< 2K token） |
| 提案 | Claude（Haiku 5.5） | 系統提示＋Doctrine（快取）＋快照＋最近 5 個事件 | `propose_orders` 工具呼叫，1～3 條建議 |
| 裁決 | 玩家 | 建議卡片 | 採納／否決／修改（寫入 battle log） |
| 執行 | Godot 驗證器 | 建議 | 合法 → 下令；不合法 → 退回＋記錄 |
| 結果 | Godot | 戰局 | 勝負、損失、據點、時間線 |
| 更新準則 | Claude（Sonnet 5.5） | 整場 battle log＋舊 Doctrine | 新 Doctrine（diff 形式）＋AAR 報告 |
| 回歸測試 | Claude（Haiku 5.5）背景 | 新 Doctrine＋戰例庫 10 個快照 | 採納率預測；退步則回滾 |

## 資料格式（草案）

### 戰局快照（送給參謀長的東西）
```json
{
  "t": 184,
  "phase": "mid",
  "objectives": [{"id": "A", "owner": "us", "contested": true}],
  "friendly": [{"id": "inf-1", "type": "infantry", "hp": 0.6, "pos": [12, 40], "state": "engaged"}],
  "enemy_known": [{"id": "e-3", "type": "armor", "pos": [20, 44], "last_seen": 170}],
  "recent_events": ["inf-2 routed at A", "armor-1 spotted e-3"],
  "player_recent_orders": [{"unit": "mg-1", "action": "hold", "target": "A"}]
}
```

### 參謀長提案（strict tool，合約而非期待）
```json
{
  "name": "propose_orders",
  "strict": true,
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["assessment", "proposals"],
    "properties": {
      "assessment": {"type": "string", "maxLength": 200},
      "proposals": {
        "type": "array", "maxItems": 3,
        "items": {
          "type": "object", "additionalProperties": false,
          "required": ["unit_id", "action", "target", "reason", "confidence"],
          "properties": {
            "unit_id": {"type": "string"},
            "action": {"type": "string", "enum": ["move", "attack", "hold", "retreat", "flank"]},
            "target": {"type": "string"},
            "reason": {"type": "string", "maxLength": 120},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
          }
        }
      }
    }
  }
}
```

### 作戰準則 doctrine.md（結構固定、有字數上限）
```markdown
# 作戰準則 v12（2026-11-01）
## 總司令風格畫像
- 偏好：先守後攻；機槍陣地優先；不喜歡分兵
## 已驗證戰術（採納率 > 70%，至少 3 場）
- R1 開局 MG 佔 A 點高地 → 採納 8/9
## 被否決的做法（不要再提）
- X1 開局裝甲單獨突進 → 否決 5/5
## 待驗證假設
- H1 玩家在落後時會接受冒險（樣本 2 場）
```

## Claude API 用法重點（依 claude-api skill 查證，2026-10 版）

- **模型**：節拍用 `claude-haiku-5-5`；AAR 用 `claude-sonnet-5-5`；都用預設 adaptive thinking，不設 `budget_tokens`（已移除）。
- **結構化輸出**：`strict: true` 工具 + `tool_choice: auto` + 系統提示明講「只用 propose_orders 回答」。（注意：新一代模型已不支援強制 `tool_choice: any/tool`。）
- **Prompt caching**：系統提示＋Doctrine 放最前面、加 `cache_control`，快照放最後；驗證 `usage.cache_read_input_tokens` > 0。
- **串流**：`messages.stream()` 讓建議卡片第一句 1 秒內出現。
- **安全護欄**：Godot 端驗證器是最後防線，LLM 輸出一律 `JSON.parse`，不用字串比對。
- ⚠️ 需老闆驗證：Godot 社群 addon「Godot LLM Framework」的 Claude 支援是否跟得上 2026 API；若不行就用 Godot 內建 `HTTPRequest` 直呼 Messages API（原始 HTTP 路線，本專案語言是 GDScript，無官方 SDK）。

## 金鑰處理（核心原則 8）

- MVP 為 BYOK：玩家在遊戲設定頁輸入金鑰，存在 Godot `user://` 目錄的加密設定檔；**不進 repo、不進對話**。
- 商業化後改成 Cloudflare Workers 薄代理，金鑰在伺服器端；屬 M4 以後，本版不做。

## 為什麼先做「文字版沙盤」（M0）

把 Godot 拿掉，用一支 Python 腳本模擬 10 回合的戰局，把快照丟給參謀長、人工裁決、跑 AAR。
兩週內就能知道「參謀長會不會變得像我」。這是整個專案最大的不確定性，應該最先驗證，而不是先花 6 週做畫面。
