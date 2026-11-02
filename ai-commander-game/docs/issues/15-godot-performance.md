# 15 效能：會戰規模 60 FPS（Compatibility，2018 內顯筆電）

> 狀態：🟡 程式完成（2026-11-02：FPS 與人數 HUD、壓力模式、無頭 CPU 基準與守門測試）；畫面 FPS 待老闆本機讀數。Blocked by 14（已驗收）。ADR-0014。

**重用**：godot-rts-kit `benchmark/` 的量測方法（固定秒數、印平均與最大）。自製：HUD 的 FPS 與人數、`-- stress=N` 壓力模式（額外 N×72 個不動的方塊人，只量畫面）、`tools/bench.gd`（無頭 CPU 基準：規模 1／5／10 倍各推進 60 秒）、`tests/test_perf.gd`（守門）。

## 驗收清單
- [ ] 老闆筆電 F5：會戰規模（126 個方塊人＋射線）穩定 ≥ 60 FPS；HUD 左上角顯示「N FPS｜人數」（老闆的 RX 7900 XTX 不是 2018 內顯的代表機，請同時貼 `-- stress=10`（1,386 人）的 FPS 當餘裕參考）
- [ ] 若不足：方塊人改 MultiMesh、射線特效合併、解算改 10 Hz；數字前後對照寫進 `docs/11`（沙盒 CPU 側已不需要）
- [x] 無頭 CPU 基準（沙盒，2026-11-02）：`tools/bench.gd -- scales=1,5,10`：1 倍 14 排 126 人 **0.34 ms/tick**（最大 2.5）、5 倍 630 人 1.70 ms、10 倍 1,260 人 3.78 ms（最大 17）；60 Hz 預算 16.7 ms，會戰規模用了 2%；`tests/test_perf.gd` 守門（1 倍 < 8 ms、5 倍 < 16.7 ms、大致線性）

## 30 秒驗收腳本
F5 → 左上角第一欄是 FPS，第二欄是人數（126）；按空白鍵交火後再看一次 FPS。然後專案設定 → 執行 → 主要執行引數填 `-- stress=10`，F5 → 人數 1,386，再看 FPS。兩個數字都 ≥ 60 就過（真正的 2018 內顯筆電要另找機器驗，先記錄高階機的餘裕）。無頭：`godot --headless --path . -s tests/test_perf.gd` → `checks: 3 (expected 3), failures: 0`。
