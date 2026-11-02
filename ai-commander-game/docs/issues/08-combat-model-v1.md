# 08 戰鬥模型 v1：兵種、科技世代、天氣地形、部署配比

> 狀態：✅ 程式完成並審查修正（2026-11-02；code-reviewer 軸 12 項全部修正；測試 123 → 157）；五場驗收已用 v1 重跑完成。後續：遊戲平衡（五場全敗 3:8）排下一張施工單。

**重用**：pydantic（表格 schema）、現有引擎結構（§4 公式改成查表）。素材面：兵種數值參考公開的二戰編制與武器資料（⚠️ 進單時列來源）。自製：修正表格式、部署階段。

## 做什麼（老闆視角）
把替身戰鬥模型換成真的：七種兵種（步兵、機槍、迫砲、反戰車、戰車、偵察、工兵）各有火力、裝甲、速度、視距、成本；地形 × 天氣 × 時段對每種兵種有不同修正（雨天泥濘裝甲慢、霧天視距短、夜間掩蔽高）；開局先在點數預算內配部隊，或選一種範本；參謀長的提示會教它這些規則，壓縮快照帶天氣與世代。全部寫在資料表，老闆可以直接改數字。

## Blocked by
02（引擎）、07（先用玩具沙盤把迴圈驗完）。

## 驗收清單
- [x] `rules/ww2_1944.json`：七種兵種 × 屬性（fire 對步兵／對裝甲、armor、speed、sight、cost、indirect）；地形 5 種 × 天氣 4 種 × 時段 2 種的修正表（移動、視距、掩蔽、裝甲通行）；表格有 schema 檢查與人話錯誤
- [x] 預留 `rules/coldwar_early.json`、`rules/coldwar_late.json` 空骨架（同 schema）
- [x] 戰情板合約 v0.2：`era`、`weather`、`time_of_day`、單位 `equipment`（可選備註，不進壓縮快照）／`cost`；`compact()` 仍 < 2K token（均衡 8 排約 450～530）
- [x] 部署階段 `chief deploy`：點數預算、三種範本（均衡／裝甲突擊／步兵固守）、參謀長可建議配比
- [x] 戰鬥解算改查表：手算三個例子（步兵 vs 戰車在雨天平地；機槍在霧夜城鎮；迫砲間接射擊）寫進 `docs/10-sim-rules.md` v1 當測試期望值
- [x] 天氣在一場中依劇本變化，事件流記「天氣轉雨」
- [x] 系統提示更新（`{rules}` 注入，約 340 token）；新敵方劇本 `samples/enemy_script_v1.json`（戰車、迫砲、反戰車；t3 雨、t6 夜、t8 霧）
- [x] 重跑 07 的 5 場驗收，準則歸零重學（2026-11-02 老闆本機，Haiku 5.5：推翻率 8.8% → 4.0% 下降；壞準則回歸 0% 退步；Ollama 一場打完；五場皆敗 3:8 → 平衡待調，見 docs/qa/m0-review.md）
- [x] 效能：10 回合解算 < 1 秒（為 M1 每 100 ms 更新鋪路）

## 30 秒驗收腳本
`uv run chief deploy --template armor` → 看到部隊清單與點數 → `uv run chief play --provider ollama --auto --template balanced --enemy samples/enemy_script_v1.json --weather fog` → 地圖標題顯示「霧／日間」、t3 事件流「天氣轉雨」、t6「進入夜間」、t8「天氣轉霧」；對照 `--weather clear` 同一 seed：第 1 回合起視距就不同（霧天看不到鄰格敵情）。注意劇本的天氣變化會蓋過開局覆寫。

## 預估檔案
`rules/ww2_1944.json`（＋冷戰骨架）、`chief/rules.py`（schema 與查表，取代原估的 rules/schema.py）、`chief/deploy.py`、`chief/sim.py`（改查表）、`chief/board.py`（v0.2）、`chief/prompts/chief_system.md`、`samples/enemy_script_v1.json`、`tests/test_rules.py`、`tests/test_combat_v1.py`（含部署測試）、`docs/09` v0.2、`docs/10` v1

## 審查紀錄（2026-11-02，code-reviewer 軸）
核心公式與 docs/10 手算全部對上；無高級別。12 項全部修正：壞 `--era`／壞板 era 由 CLI 以人話退回；劇本 `weather_changes`／`time_changes` 改 Literal 驗值；`mixed` 葉節點開局即退回；`--era` 不搭部署也生效；潰散只退 1 格；工兵加成要 hold 該格；過河以回合開始工兵位置為準（不隨 id 序變）；`armor` 不論版本一律轉 `tank`；`{rules}` 掛點缺失時附在結尾並警告；補 `equipment` 欄位；快速單位進敵格即停；提示補迫砲觀測條件；地圖標題帶天氣；補 11 個測試（含 `chief sim --template`、`--suggest` 斷言）。
