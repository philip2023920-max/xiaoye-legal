# 03 技術架構草案

> 文件狀態：🟡 v0.3（2026-11-01，加入 Token 計量、戰報卡與討論）｜對應心智圖節點：`4. 技術架構`
> 重用優先（ADR-0011）：每一層的候選現成元件見 `07-reuse-catalog.md`。
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
│ 2. 戰鬥沙盤層（Godot 4，ADR-0001；M0 先用 Python 模擬）       │
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
- 玩家接管某一級後，該節點與其子節點標記為「總司令直轄」，LLM 的戰情板上看得到這個標記，不會再對它下令（驗證器 V2）。「請求歸還」M0 不做，留 M2 畫面。
- 每次接管都產生一筆 **推翻紀錄**：AI 原令、玩家改令、當時戰情板快照、後果（30 秒／戰後）。這是成長迴圈最重要的訓練訊號。

## 規模階梯（解決「軍團」與「低硬體」的衝突，ADR-0008）

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

側欄顯示：分區地圖（ASCII 風格或簡圖）、部隊樹（可折疊）、事件流、參謀長的最近一句話與命令。M0 終端機版用 **Textual** 的 Tree／DataTable 元件；單位符號可借 **milsymbol** 預渲染（重用，見 `07-reuse-catalog.md`）。

## 參謀長命令（結構化合約）

```json
{
  "name": "issue_orders",
  "input_schema": {
    "type": "object", "additionalProperties": false,
    "required": ["assessment", "orders"],
    "properties": {
      "assessment": {"type": "string", "maxLength": 200},
      "orders": {"type": "array",
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

驗證器檢查（V1～V7，見 `10-sim-rules.md` §10）：單位存在且未殲滅、不是玩家直轄、目標型別正確、一單位一令、一回合最多 5 條（第 6 條起退回）、潰散只能撤退、同一指揮鏈一回合一條令。

## LLM 閘道（多供應商，ADR-0003；首批 Anthropic＋Ollama，ADR-0009）

```
遊戲 ──▶ prompts.build_messages(doctrine, snapshot, turn, lang, feedback)
     ──▶ Gateway.issue_orders(messages) -> ChiefResponse(orders | None, usage, attempts, error)
             ├─ AnthropicGateway   官方 SDK messages.parse() 結構化輸出；系統提示＋準則 cache_control；串流延後 M2
             └─ LiteLLMGateway     instructor MD_JSON（容忍圍欄）；Ollama 走 json_schema → json_object → 純提示 三段降級；
                                   OpenAI、DeepSeek、OpenRouter、LM Studio、vLLM… 同一路徑
```
（M0 實作，2026-11-01；原草案的 `issue_orders(snapshot, doctrine)` 已改為上述分工）

- **重用**：OpenAI 相容 adapter 以 **LiteLLM** 實作（統一 usage、價格表）；結構化輸出與重試以 **instructor** 實作；Anthropic 原生 adapter 自寫以用 strict tool 與 prompt caching（⚠️ 進 Stage 2 驗證）。
- **最低公分母**：所有供應商都走「系統提示附 JSON Schema → 回傳 JSON → 本地驗證 → 不合格重試最多 2 次」。有原生 strict 模式的（Anthropic 結構化輸出、Ollama `format=<schema>`、OpenAI `json_schema`）就開，沒有的靠驗證器。
- **寬進嚴出**：schema 層只做正規化（截斷、同義詞、大小寫），不因小毛病整筆打回；硬規則由驗證器 V1～V7 執行（否則 3B 小模型一回合裡任何一點不合就「整回合無命令」）。
- **供應商能力表** `provider.json`：adapter、strict schema、json mode、串流、費用類型；價格另在 `chief/prices.json`（每百萬 token 美元，覆寫 LiteLLM 內建表）。
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
- 對決不設限制（ADR-0010）：任何包搭任何模型。對決畫面與排行榜必須顯示雙方模型與每場花費，讓「DeepSeek vs Fable」本身成為看點。

## Token 計量與費用估算（F13）

```
每次 LLM 呼叫 ──▶ UsageMeter.record(provider, model, in, out, cache_read, cache_write, latency)
                      │
                      ├─ 來源 A：供應商回傳的 usage 欄位（Anthropic usage、OpenAI usage、
                      │          Ollama 的 prompt_eval_count / eval_count）
                      ├─ 來源 B：沒回傳時用本地估算（字元數 ÷ 4，標記「估」）
                      └─ 價格表 prices.json（每百萬 token 輸入／輸出／快取讀寫；玩家可編輯；
                         附「最後更新日期」提醒）
                      ▼
            battles/<id>/usage.jsonl（本場）＋ battles/ledger.jsonl（跨場帳本）──▶ HUD：本場 $0.04｜今天 $0.31｜本月 $2.10
                                       ──▶ 預算：玩家設上限，到 80% 提醒，到 100% 可選「暫停參謀長」
```

- 本地模型：費用顯示 $0，但仍顯示 token 與秒數（讓玩家感受模型大小的代價）。
- 對決模式：兩側各自計量，戰報卡上並列「這場 DeepSeek 花 $0.02，Fable 花 $0.40」。
- 價格會變，⚠️ 價格表在建置時要重新查官方頁面；遊戲只做估算，介面明寫「估算值，以供應商帳單為準」。

## 戰報卡與討論（F14，遊戲化、從簡）

設計原則：**一張卡、三幕、三回合、一個按鈕**。玩家 2 分鐘內做完，不想做可以跳過。

```
┌─ 戰報卡 ──────────────────────────────────────────┐
│ 勝 ★★☆   會戰 12 分鐘   推翻 3 次   花費 $0.06     │
│ 🎖️ 徽章：果斷總司令（推翻後 30 秒內戰果改善 2 次）  │
│                                                    │
│ 關鍵三幕（自動挑選推翻點與轉折點）                  │
│  ① t3:10  AI：連 A 側翼  │ 你：改為固守  │ 結果 👍  │
│  ② t6:40  AI：預備隊投入 │ 你：沒動      │ 結果 👎  │
│  ③ t9:05  AI：撤出 B 點  │ 你：同意      │ 結果 👍  │
│                                                    │
│ 參謀長：「您在落後時偏好固守，我下次會先問再衝。」 │
│                      [ 討論 ]   [ 直接採納 ]  [ 跳過 ] │
└────────────────────────────────────────────────────┘
```

- **三幕怎麼挑**：優先推翻點（玩家 vs AI 的真實分歧），不足三個再補戰局轉折點（據點易手、部隊潰散）。每幕只顯示：時間、AI 的令、玩家的令、後果（30 秒內友軍戰力與據點變化，簡化為 👍／👎／➖）。
- **討論怎麼從簡**：最多三回合。每回合畫面給 3 個快速回覆（例如「為什麼第②幕不投預備隊？」「下次這種情況先問我」「我錯了，照你的」），也可打字。AI 回覆限 2 句。第三回合結束自動進入採納畫面。
- **採納畫面**：顯示準則 diff（新增／刪除各最多 3 條，一行一條），一鍵「採納」或「不採納」；採納後下一場開局時參謀長會引用它（「上次您說……」），讓玩家看到成長閉環。
- **遊戲化元素**：徽章（M0 四種：果斷總司令、放手型、省錢贏家＝獲勝且本場費用 < $0.01、守土有責；「用便宜模型打贏強模型」要等對決模式）、信任計量條與連勝紀錄留 M2 畫面。徽章規則全部可離線判定，不花 token。
- **技術上**：戰報卡由程式從推翻紀錄與事件流產生，**不呼叫 LLM**；只有「參謀長一句話」與「討論」用 LLM（節拍同級模型），準則 diff 用 AAR 模型（anthropic 預設 Sonnet 5.5，其他供應商預設同節拍模型，`--aar-provider/--aar-model` 可改）。戰後呼叫全部計入計量（phase=aar），自動模式只出卡不呼叫 LLM。準則檔多一段 `## Last adopted` 供下一場開局引用；超過 2,000 字先淘汰最舊的假設 → 戰術 → 被否決 → 畫像（剛新增的不淘汰）。

## 成長迴圈（每場戰後）

```
推翻紀錄＋戰果 ──▶ AAR 檢討官（較強模型）──▶ Doctrine diff
                                                │
      回滾 ◀── 退步 ◀── 戰例庫回歸（便宜模型）◀───┘
```

Doctrine 結構（有上限 2,000 字）：總司令風格畫像／已驗證戰術／被推翻的做法／待驗證假設。語言依 D7：介面三語，準則預設英文＋玩家語言摘要。

## 為什麼 M0 先做戰情板＋文字沙盤

戰情板是整個系統的中樞：引擎往裡寫、LLM 從裡讀、玩家側欄看它、AAR 回放它。M0 用 Python 模擬一場會戰把戰情板、閘道、命令合約、推翻紀錄、AAR 全部跑通，引擎決定（D1）可以延後到 M0 之後再拍。
