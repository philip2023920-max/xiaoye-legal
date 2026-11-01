# 03 技術架構草案

> 文件狀態：🟡 v0.2（2026-11-01，依老闆第一輪拍板改版）｜對應心智圖節點：`4. 技術架構`
> ⚠️ 仍是 Stage 1 方向草案。正式選型、環境建置、ADR 細節要等老闆說「進入 Stage 2」。

## 系統分層（由下往上）

```
┌──────────────────────────────────────────────────────────┐
│ 5. 成長迴圈層（Harness）                                   │
│    AAR 檢討官 → 更新 Doctrine → 戰例庫回歸 → 回滾           │
│    參謀長包（匯出／匯入）、參謀長對決、官方挑戰包            │
├──────────────────────────────────────────────────────────┤
│ 4. 參謀長層（LLM Agent）                                   │
│    讀戰情板 → LLM 閘道（多供應商）→ 結構化命令 → 驗證器      │
├──────────────────────────────────────────────────────────┤
│ 3. AI 戰情板（常駐、給 AI 看的沙盤）                        │
│    分區地圖、部隊樹（班排連旅軍團）、事件流、目標、迷霧       │
│    遊戲中以側欄即時顯示給玩家                                │
├──────────────────────────────────────────────────────────┤
│ 2. 戰鬥沙盤層（引擎，D1 待定；M0 先用 Python 模擬）          │
│    單位、地圖、簡化物理、編制 AI、玩家接管 UI                 │
├──────────────────────────────────────────────────────────┤
│ 1. 資料層（本機檔案）                                       │
│    harness/<名稱>/doctrine.md、prompts/、provider.json、     │
│    battles/*.jsonl、evals/                                   │
└──────────────────────────────────────────────────────────┘
```

比喻：第 2 層是戰場，第 3 層是參謀長桌上的沙盤（玩家也看得到同一個沙盤），第 4 層是參謀長本人，第 5 層是他晚上寫日記、整理筆記的習慣，第 1 層是那本筆記本；「參謀長包」就是把筆記本連同他的做事方法一起裝箱帶走。

## 指揮鏈：LLM 管意圖，程式管執行

| 層級 | 誰下令 | 誰執行 | 玩家能接管嗎 |
|---|---|---|---|
| 軍團／旅 | 參謀長（LLM） | 編制 AI 拆成連級任務 | 能 |
| 連／排 | 參謀長（LLM）或編制 AI | 編制 AI：路徑、間距、交戰 | 能 |
| 班 | 編制 AI | 單位腳本：移動、射擊、掩蔽 | 能（直接點選） |

- LLM **不逐單位微操**，它對編制下「任務式命令」（佔領、固守、側翼、撤退、支援），這才對得上 2～10 秒的延遲。
- 玩家接管某一級後，該節點與其子節點標記為「總司令直轄」，LLM 的戰情板上看得到這個標記，不會再對它下令，但可以「請求歸還」。
- 每次接管都產生一筆 **推翻紀錄**：AI 原令、玩家改令、當時戰情板快照、後果（30 秒／戰後）。這是成長迴圈最重要的訓練訊號。

## 規模階梯（解決「軍團」與「低硬體」的衝突，D8）

| 規模 | 可控層級 | 渲染方式 | 物理 |
|---|---|---|---|
| 遭遇戰 | 班／排（20～100 人） | 每個士兵一個方塊人 | 死亡 ragdoll |
| 會戰 | 連／旅（500～2,000 人） | 一個班＝一組 3 個方塊人代表 10 人 | 只有鏡頭附近的班有 ragdoll |
| 大會戰 | 旅／軍團（5,000 人以上） | 連以上用棋子，拉近鏡頭才展開成方塊人 | 棋子無物理 |

TABS 式「每個人都是布娃娃」只在遭遇戰規模成立；會戰以上必須用細節層級（LOD）。這是物理現實，不是取捨。

## AI 戰情板（給 AI 看的沙盤）

設計原則：**人與 AI 看同一份**。遊戲引擎每 100 ms 更新一次，LLM 在節拍時讀取壓縮版。

```json
{
  "t": 184, "phase": "mid", "scale": "battle",
  "map": {"sectors": {"A1": {"terrain": "hill", "owner": "us", "contested": true}}},
  "orbat": [
    {"id": "co-A", "echelon": "company", "parent": "bde-1", "strength": 0.72,
     "state": "engaged", "sector": "A1", "task": "hold", "controlled_by": "ai",
     "children": ["plt-A1", "plt-A2", "plt-A3"]}
  ],
  "enemy_known": [{"id": "e-co-3", "echelon": "company", "sector": "B2", "last_seen": 170}],
  "events": ["t180 plt-A2 routed in A1", "t176 player took control of co-B"],
  "objectives": [{"id": "A1", "value": 3, "owner": "us"}],
  "overrides_this_battle": 2
}
```

側欄顯示：分區地圖（ASCII 風格或簡圖）、部隊樹（可折疊）、事件流、參謀長的最近一句話與命令。

## 參謀長命令（結構化合約）

```json
{
  "name": "issue_orders",
  "input_schema": {
    "type": "object", "additionalProperties": false,
    "required": ["assessment", "orders"],
    "properties": {
      "assessment": {"type": "string", "maxLength": 200},
      "orders": {"type": "array", "maxItems": 5,
        "items": {"type": "object", "additionalProperties": false,
          "required": ["unit_id", "task", "target", "reason"],
          "properties": {
            "unit_id": {"type": "string"},
            "task": {"type": "string", "enum": ["seize", "hold", "flank", "withdraw", "support", "reserve"]},
            "target": {"type": "string"},
            "reason": {"type": "string", "maxLength": 120}
          }}}
    }
  }
}
```

驗證器檢查：單位存在且不是玩家直轄、目標分區存在、任務與編制層級相符、同一單位一次只有一個令。

## LLM 閘道（多供應商，D3）

```
遊戲 ──▶ LLMGateway.issue_orders(snapshot, doctrine)
             ├─ AnthropicAdapter      原生 Messages API；strict tool；prompt caching；串流
             ├─ OpenAICompatAdapter   /v1/chat/completions；OpenAI、Gemini（OpenAI 相容端點）、
             │                        Ollama、LM Studio、vLLM、OpenRouter、DeepSeek…
             └─ （預留）GeminiNative、本地 llama.cpp
```

- **最低公分母**：所有供應商都走「系統提示附 JSON Schema → 回傳 JSON → 本地驗證 → 不合格重試最多 2 次」。有原生 strict 模式的（Anthropic strict tool、OpenAI `json_schema`）就開，沒有的靠驗證器。
- **供應商能力表** `provider.json`：是否支援 strict schema、串流、快取、最大 context、每千 token 價格；介面據此顯示「此模型可能較常被退回」提示。
- **研究結果**：OpenAI 相容端點的 schema 強制程度參差（有的接受 `response_format` 但不強制；Gemini 對 `items` 要明確型別；本地模型最不可預測）→ 客戶端驗證是必備，不是加分。⚠️ Anthropic 的 OpenAI 相容端點是否支援 `response_format` 未查證，本專案對 Anthropic 一律走原生 API。
- **金鑰**：每個供應商一個欄位，存 `user://` 加密設定；本地模型不需金鑰。

## 參謀長包（Harness 格式，F9／F10）

```
harness/<名稱>/
  manifest.json     名稱、版本、作者、適用規模、語言
  doctrine.md       作戰準則
  prompts/          系統提示模板（英文為主，附語言指令）
  provider.json     建議供應商與模型（不含金鑰）
  evals/            戰例庫成績（採納率、模擬戰果）
```

- 匯出＝打包成 zip；匯入＝解壓驗證 manifest。
- **參謀長對決**：遊戲同時開兩個閘道實例，各讀一個包、各指揮一方；玩家可旁觀或接管一方。
- **官方挑戰包**：老闆釋出的參謀長包放在 GitHub Releases，遊戲內可一鍵下載。
- 排名靠「同一組戰例、同一模型」的對戰結果，避免拿貴模型碾壓。

## 成長迴圈（每場戰後）

```
推翻紀錄＋戰果 ──▶ AAR 檢討官（較強模型）──▶ Doctrine diff
                                                │
      回滾 ◀── 退步 ◀── 戰例庫回歸（便宜模型）◀───┘
```

Doctrine 結構（有上限 2,000 字）：總司令風格畫像／已驗證戰術／被推翻的做法／待驗證假設。語言依 D7：介面三語，準則預設英文＋玩家語言摘要。

## 為什麼 M0 先做戰情板＋文字沙盤

戰情板是整個系統的中樞：引擎往裡寫、LLM 從裡讀、玩家側欄看它、AAR 回放它。M0 用 Python 模擬一場會戰把戰情板、閘道、命令合約、推翻紀錄、AAR 全部跑通，引擎決定（D1）可以延後到 M0 之後再拍。
