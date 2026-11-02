# 15 效能：會戰規模 60 FPS（Compatibility，2018 內顯筆電）

> 狀態：⬜。Blocked by 14。ADR-0014。

**重用**：godot-rts-kit `benchmark/` 的量測方法（CSV）。自製：FPS 計數 HUD、`tools/bench.gd`（無頭跑 60 秒印平均幀時間；畫面 FPS 只能老闆本機看）。

## 驗收清單
- [ ] 老闆筆電 F5：會戰規模（135 個方塊人）穩定 ≥ 60 FPS；HUD 顯示 FPS 與單位數
- [ ] 若不足：方塊人改 MultiMesh、射線特效合併、解算改 10 Hz；數字前後對照寫進 `docs/11`
- [ ] 無頭基準：`godot --headless -s tools/bench.gd` 印平均 `_physics_process` 毫秒（沙盒跑，當回歸守門）
