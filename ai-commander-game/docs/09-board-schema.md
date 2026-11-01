# 09 戰情板（Board）資料合約 v0.1

> 施工單 01 產出｜程式：`m0/chief/board.py`｜範例：`m0/samples/board_t0.json`
> 這是所有層共用的合約：引擎每 100 ms 寫入（M0 每回合）、LLM 在節拍讀 `compact()`、玩家側欄渲染它、戰報卡回放它。改欄位要連文件與測試一起改。

## 頂層

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema_version` | 字串 | 目前 `"0.1"` |
| `battle_id` | 字串 | 這場會戰的識別 |
| `t` | 整數 | 時間；M0 是回合數，M1 起是秒 |
| `time_unit` | `turn` / `second` | `t` 的單位 |
| `phase` | `early` / `mid` / `late` | 戰局階段（給 LLM 判斷節奏） |
| `scale` | `skirmish` / `battle` / `grand` | 規模階梯（ADR-0008）：遭遇戰／會戰／大會戰 |
| `map` | MapGrid | 分區地圖 |
| `orbat` | Unit[] | 友軍部隊樹（扁平列表，用 `parent` 連結） |
| `enemy_known` | Contact[] | 已知敵情（只記看過的，不是敵方真實狀態） |
| `objectives` | Objective[] | 目標 |
| `events` | Event[] | 事件流（時間順序） |
| `fog` | Fog | 戰爭迷霧 |
| `overrides_this_battle` | 整數 | 本場總司令推翻次數 |

## MapGrid

| 欄位 | 說明 |
|---|---|
| `cols`、`rows` | 格數；分區 id 用「欄字母＋列數」如 `B2`，A 在左、1 在上 |
| `sectors` | 以 id 為鍵的 Sector 表，必須涵蓋全部格子，不多不少 |

## Sector

| 欄位 | 說明 |
|---|---|
| `terrain` | `open` 平地／`hill` 高地／`forest` 森林／`town` 城鎮／`river` 河川 |
| `owner` | `us`／`enemy`／`none` |
| `contested` | 是否爭奪中 |
| `cover` | 掩蔽度 0～1，影響戰損（戰損公式見 `10-sim-rules.md`） |
| `objective` | 此分區的目標 id；必須與 `objectives` 表互相對得上 |

## Unit（友軍部隊）

| 欄位 | 說明 |
|---|---|
| `id`、`name` | 識別與顯示名 |
| `echelon` | `squad` 班／`platoon` 排／`company` 連／`battalion` 營／`brigade` 旅／`army_group` 軍團 |
| `type` | `infantry`／`mg`／`armor`／`mixed` |
| `parent` | 上級 id；上級層級必須比自己高 |
| `strength` | 戰力 0～1 |
| `state` | `idle` 待命／`moving`／`engaged` 交戰／`routed` 潰散／`destroyed` 殲滅 |
| `sector` | 所在分區 |
| `task` | 目前任務 `{type, target}`；`type` 六種：`seize` 奪取／`hold` 固守／`flank` 側翼／`withdraw` 撤退／`support` 支援／`reserve` 預備；`target` 是分區 id（support 可為友軍 id） |
| `controlled_by` | `ai`（參謀長）／`player`（總司令直轄；參謀長不得對它下令） |

## Contact（已知敵情）

| 欄位 | 說明 |
|---|---|
| `id`、`echelon`、`type`、`sector` | 同上 |
| `strength_est` | 估計戰力 0～1 |
| `last_seen` | 最後目擊的 `t` |
| `confidence` | 可信度 0～1 |

## Objective、Event、Fog

- Objective：`id`、`sector`、`value`（≥1，計分權重）、`owner`
- Event：`t`、`kind`（`contact`／`order`／`override`／`routed`／`seized`／`info`…）、`text`（人話）、可選 `unit`、`sector`
- Fog：`visible_sectors` 可見分區列表；空列表代表全圖可見

## 一致性檢查（載入時擋下，訊息是繁中人話）

部隊 id 重複、parent 不存在、上級層級不高於自己、分區不在地圖、任務目標既非分區也非友軍、目標與分區標記不一致、迷霧分區不存在、地圖缺格或多格。

## `compact()`：給 LLM 的壓縮版

英文鍵值、去掉殲滅單位、分區壓成 `"hill/us/O1/contested"` 字串、只留最近 5 筆事件。範例檔壓縮後離線粗估約 500 token（上限 2,000；粗估法：ASCII 4 字元＝1、非 ASCII 1 字＝1，正式計量以供應商 usage 為準）。

```json
{"t":3,"unit":"turn","phase":"mid","scale":"battle",
 "map":{"size":"5x5","sectors":{"A1":"open/us","B2":"hill/us/O1", "...":"..."}},
 "visible":["A1","A2","..."],
 "friendly":[{"id":"co-A","ech":"company","type":"mixed","str":0.82,"state":"engaged","sector":"B2","task":"hold B2"},
             {"id":"plt-A3","ech":"platoon","type":"mg","str":0.8,"state":"idle","sector":"B1","task":"hold B1","parent":"co-A","ctrl":"player"}],
 "enemy":[{"id":"e-co-1","ech":"company","type":"mixed","sector":"D4","str":0.9,"seen":2,"conf":0.6}],
 "objectives":[{"id":"O1","sector":"B2","value":3,"owner":"us"}],
 "events":["t3 參謀長令 A2 排奪取 C3 城鎮"],
 "overrides":1}
```

## 看範例

```bash
uv run chief show samples/board_t0.json
uv run chief show samples/board_t0.json --compact
```
