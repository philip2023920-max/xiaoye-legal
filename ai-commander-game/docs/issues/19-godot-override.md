# 19 推翻與接管 UI

> 狀態：⬜。Blocked by 18。ADR-0015（D29）；規則 docs/10 §9、§10 V2。

**重用**：骨架 `RTSSelection`（點排）、`RTSCameraRig.ground_at`（點地圖選分區）；M1 `Orbat.apply_orders(issuer="player")`、`controlled_by`；16 的 `/override` 與後果判定。自製：`scripts/ui/override_panel.gd`、直轄標記（排的環改色）。

## 驗收清單
- [ ] 點地圖上的排或側欄的排／連 → 面板：單位名、目前任務、六種任務按鈕、「點地圖選目標」（support 改成點友軍）、「接管」「放手」
- [ ] 下令：`apply_orders("us", [Order(issuer="player")])`，該單位（含連的子排）`controlled_by=player`、環變金色；參謀長下一 tick 不碰（服務端 V2 退回會出現在 feedback）；「放手」還給參謀長
- [ ] 每次改掉參謀長的令或接管沒令的單位 → POST `/override`（ai_order＝該單位最近一次參謀長的令或 null）；30 秒後事件流顯示後果 👍／👎／➖
- [ ] 推翻率顯示在側欄（推翻次數／參謀長放行命令數，§9 定義）
- [ ] 無頭測試：面板狀態機、接管連含子排、放手、推翻記錄內容

## 30 秒驗收腳本
F5 → 點 A3 排 → 固守 → 點 B1 → 看環變金、事件流「總司令接管 A3 排」→ 30 秒後 👍。

## 來自施工單 16 二審的待辦
- 服務以每拍的板釋放直轄單位：同一拍內「放手→再接管」不會算第二次推翻。若要精確，19 要在放手時送 `/override` 的 `released: [ids]`（或新端點 `/release`），並改 docs/10 §16。
