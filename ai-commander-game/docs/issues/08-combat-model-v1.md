# 08 戰鬥模型 v1：兵種、科技世代、天氣地形、部署配比

**重用**：pydantic（表格 schema）、現有引擎結構（§4 公式改成查表）。素材面：兵種數值參考公開的二戰編制與武器資料（⚠️ 進單時列來源）。自製：修正表格式、部署階段。

## 做什麼（老闆視角）
把替身戰鬥模型換成真的：七種兵種（步兵、機槍、迫砲、反戰車、戰車、偵察、工兵）各有火力、裝甲、速度、視距、成本；地形 × 天氣 × 時段對每種兵種有不同修正（雨天泥濘裝甲慢、霧天視距短、夜間掩蔽高）；開局先在點數預算內配部隊，或選一種範本；參謀長的提示會教它這些規則，壓縮快照帶天氣與世代。全部寫在資料表，老闆可以直接改數字。

## Blocked by
02（引擎）、07（先用玩具沙盤把迴圈驗完）。

## 驗收清單
- [ ] `rules/ww2_1944.json`：七種兵種 × 屬性（fire 對步兵／對裝甲、armor、speed、sight、cost、indirect）；地形 5 種 × 天氣 4 種 × 時段 2 種的修正表（移動、視距、掩蔽、裝甲通行）；表格有 schema 檢查與人話錯誤
- [ ] 預留 `rules/coldwar_early.json`、`rules/coldwar_late.json` 空骨架（同 schema）
- [ ] 戰情板合約 v0.2：`era`、`weather`、`time_of_day`、單位 `equipment`／`cost`；`compact()` 仍 < 2K token
- [ ] 部署階段 `chief deploy`：點數預算、三種範本（均衡／裝甲突擊／步兵固守）、參謀長可建議配比
- [ ] 戰鬥解算改查表：手算三個例子（步兵 vs 戰車在雨天平地；機槍在霧夜城鎮；迫砲間接射擊）寫進 `docs/10-sim-rules.md` v1 當測試期望值
- [ ] 天氣在一場中依劇本變化，事件流記「天氣轉雨」
- [ ] 系統提示更新；新敵方劇本（含裝甲與砲兵）；重跑 07 的 5 場驗收，準則歸零重學
- [ ] 效能：10 回合解算 < 1 秒（為 M1 每 100 ms 更新鋪路）

## 30 秒驗收腳本
`uv run chief deploy --template armor` → 看到部隊清單與點數 → `uv run chief play --provider ollama --auto --weather rain --time night` → 事件流有天氣影響的紀錄，戰果與晴天不同。

## 預估檔案
`rules/ww2_1944.json`、`rules/schema.py`、`chief/deploy.py`、`chief/sim.py`（改查表）、`chief/board.py`（v0.2）、`chief/prompts/chief_system.md`、`samples/enemy_script_v1.json`、`tests/test_rules.py`、`tests/test_deploy.py`、`docs/09`、`docs/10` v1
