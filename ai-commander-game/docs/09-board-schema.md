# 09 戰情板（Board）資料合約 v0.2

> 施工單 01 產出、施工單 08 升到 v0.2｜程式：`m0/chief/board.py`｜範例：`m0/samples/board_start.json`、`board_t0.json`
> v0.2（2026-11-02）：新增 `era`、`weather`、`time_of_day`、單位 `cost`；兵種七種；載入 0.1 檔自動升級（補預設值、`armor` → `tank`）。
> 這是所有層共用的合約：引擎每 100 ms 寫入（M0 每回合）、LLM 在節拍讀 `compact()`、玩家側欄渲染它、戰報卡回放它。改欄位要連文件與測試一起改。

## 頂層

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema_version` | 字串 | 目前 `"0.2"`；`"0.1"` 檔載入時自動升級（`upgrade_dict`），其他版本拒收 |
| `battle_id` | 字串 | 這場會戰的識別 |
| `t` | 整數 | 時間；M0 是回合數，M1 起是秒 |
| `time_unit` | `turn` / `second` | `t` 的單位 |
| `phase` | `early` / `mid` / `late` | 戰局階段（給 LLM 判斷節奏）；預設 `early` |
| `scale` | `skirmish` / `battle` / `grand` | 規模階梯（ADR-0008）：遭遇戰／會戰／大會戰；預設 `battle` |
| `era` | 字串 | 世代規則檔名（`m0/rules/<era>.json`）；預設 `ww2_1944`。引擎與系統提示都照它查表 |
| `weather` | `clear` 晴／`rain` 雨／`snow` 雪／`fog` 霧 | 目前天氣；預設 `clear`；一場中可依敵方劇本變化 |
| `time_of_day` | `day`／`night` | 目前時段；預設 `day` |
| `time_unit` | | 預設 `turn` |
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
| `cols`、`rows` | 格數（cols 1～26、rows 1～99）；分區 id 用「欄字母＋列數」如 `B2`，A 在左、1 在上 |
| `sectors` | 以 id 為鍵的 Sector 表，必須涵蓋全部格子，不多不少；每筆的 `id` 必須等於鍵 |

## Sector

| 欄位 | 說明 |
|---|---|
| `terrain` | `open` 平地／`hill` 高地／`forest` 森林／`town` 城鎮／`river` 河川；預設 `open` |
| `owner` | `us`／`enemy`／`none`；預設 `none` |
| `contested` | 是否爭奪中；預設 `false` |
| `cover` | 掩蔽度 0～1，影響戰損（公式見 `10-sim-rules.md` §4）；省略時用地形預設值（`rules/<era>.json` 的 `terrain.cover`） |
| `objective` | 此分區的目標 id。**雙向檢查**：分區標了目標就必須在目標表；目標表的每個目標，其分區也必須標回來 |

## Unit（友軍部隊）

| 欄位 | 說明 |
|---|---|
| `id`、`name` | 識別與顯示名；`id` 不得與任何分區 id 同名、不得重複 |
| `echelon` | `squad` 班／`platoon` 排／`company` 連／`battalion` 營／`brigade` 旅／`army_group` 軍團 |
| `type` | 七種兵種 `infantry` 步兵／`mg` 機槍／`mortar` 迫砲／`at` 反戰車／`tank` 戰車／`recon` 偵察／`engineer` 工兵；`mixed` 是連級容器；舊名 `armor` 載入時轉成 `tank`；預設 `infantry` |
| `parent` | 上級 id；上級層級必須比自己高；不能是自己 |
| `strength` | 戰力 0～1；預設 `1.0` |
| `state` | `idle` 待命／`moving`／`engaged` 交戰／`routed` 潰散／`destroyed` 殲滅；預設 `idle`。殲滅單位留在部隊樹供回放，但 `units_in()` 與 `compact()` 不算它 |
| `sector` | 所在分區 |
| `task` | 目前任務 `{type, target}`；`type` 六種：`seize` 奪取／`hold` 固守／`flank` 側翼／`withdraw` 撤退／`support` 支援／`reserve` 預備。`target`：`support` 必須是友軍單位 id（不能是自己）；其他五種必須是分區 id |
| `controlled_by` | `ai`（參謀長）／`player`（總司令直轄；參謀長不得對它下令）；預設 `ai` |
| `cost` | 部署點數（v0.2；`chief deploy` 填入，0＝未計） |

## Contact（已知敵情）

| 欄位 | 說明 |
|---|---|
| `id`、`echelon`、`type`、`sector` | 同上 |
| `strength_est` | 估計戰力 0～1；預設 `1.0` |
| `last_seen` | 最後目擊的 `t` |
| `confidence` | 可信度 0～1；預設 `0.5` |
| | `id` 不得重複 |

## Objective、Event、Fog

- Objective：`id`（不得重複）、`sector`、`value`（≥1，計分權重）、`owner`（預設 `none`）
- Event：`t`、`kind`（`contact`／`order`／`override`／`routed`／`seized`／`destroyed`／`info`…）、`text`（人話）、可選 `unit`、`sector`。時間順序由寫入方負責，載入時不強制
- Fog：`visible_sectors` 可見分區列表；空列表代表全圖可見（`compact()` 會輸出 `"visible":"all"` 講明白）

## 一致性檢查（載入時擋下，訊息是繁中人話）

版本不符、部隊／敵情／目標 id 重複、部隊 id 與分區同名、parent 不存在或是自己、上級層級不高於自己、分區不在地圖、support 目標不是友軍或是自己、其他任務目標不是分區、目標與分區標記不一致（雙向）、迷霧分區不存在、地圖缺格或多格。常見的型別錯誤（缺欄位、選項不對、超出範圍）也翻成繁中。檔案開頭的 BOM 可容忍。

## `compact()`：給 LLM 的壓縮版

英文鍵值、去掉殲滅單位（上級若已殲滅，子單位不留 `parent`）、分區壓成 `"hill/us/O1/contested"` 字串、迷霧空列表輸出 `"all"`、只留最近 5 筆事件；v0.2 多 `era`、`weather`、`time` 三個鍵。範例檔壓縮後離線粗估約 500 token（均衡範本 8 個排約 450）（上限 2,000；粗估法：ASCII 4 字元＝1、非 ASCII 1 字＝1，正式計量以供應商 usage 為準）。

```json
{"t":3,"unit":"turn","phase":"mid","scale":"battle","era":"ww2_1944","weather":"clear","time":"day",
 "map":{"size":"5x5","sectors":{"A1":"open/us","B2":"hill/us/O1", "...":"..."}},
 "visible":["A1","A2","..."],
 "friendly":[{"id":"co-A","ech":"company","type":"mixed","str":0.82,"state":"engaged","sector":"B2","task":"hold B2"},
             {"id":"plt-A3","ech":"platoon","type":"mg","str":0.8,"state":"idle","sector":"B1","task":"hold B1","parent":"co-A","ctrl":"player"}],
 "enemy":[{"id":"e-co-1","ech":"company","type":"mixed","sector":"D4","str":0.9,"seen":2,"conf":0.6}],
 "objectives":[{"id":"O1","sector":"B2","value":3,"owner":"us"}],
 "events":["t3 參謀長令 A2 排奪取 C3 城鎮"],
 "overrides":1}
```

## 終端機字元

預設用 ASCII（`. ^ T # ~ *`），Windows 中文主控台與東亞寬度不定的字型都安全；UTF-8 終端機想看圖形字元可設環境變數 `CHIEF_FANCY=1`。

## 看範例

```bash
uv run chief show samples/board_t0.json
uv run chief show samples/board_t0.json --compact
```
