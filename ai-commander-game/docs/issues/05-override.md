# 05 總司令推翻與接管（終端機）

**重用**：Rich（表格、面板）＋標準 `input()` 提示迴圈。自製：推翻紀錄與後果判定。
> 偏離原計畫：M0 的回合制互動用提示迴圈比 Textual 全螢幕 App 簡單、可測（注入 input），Textual 留給 M2 的即時畫面。決策 S2 的操作方式照辦（Enter 全採納、數字改令：選任務 → 選目標）。

## 做什麼（老闆視角）
把自動打改成「參謀長先下令，老闆看一眼再放行」：每回合畫面列出參謀長的命令，按 Enter 全部採納；或選一條改掉（選單位 → 選任務 → 選目標），該單位就變成「總司令直轄」，參謀長之後不再對它下令，直到老闆放手。每次推翻都記下：AI 原令、你的令、當時沙盤、下一回合後果 👍👎➖。

## Blocked by
03（可與 04 並行）。

## 驗收清單
- [ ] `uv run chief play --provider ollama`（不加 `--auto`）進入互動模式，每回合可 Enter 採納或改令
- [x] 改令後戰情板該單位 `controlled_by: player`，下一回合參謀長的命令不含該單位（驗證器擋下並記錄）
- [x] 「放手」操作讓單位回到 `ai`
- [x] 推翻紀錄寫入 `battles/<id>/overrides.jsonl`，欄位：turn、unit_id、ai_order、player_order、snapshot_ref（推翻當下的上一回合快照，第 1 回合指向開局快照 t0.json）、strength_at、outcome、judged_turn
- [x] 後果判定：下一回合該單位戰力與所在據點變化 → 👍／👎／➖，規則與手算例子寫在 `docs/10-sim-rules.md`
- [x] 戰後印「推翻率：n/m」

## 30 秒驗收腳本
`uv run chief play --provider ollama` → 第 1 回合選一條命令改成「hold」→ 看到該單位標記為直轄 → 第 2 回合參謀長沒再對它下令 → 戰後印推翻率。

## 預估檔案
`chief/override.py`、`chief/play.py`（互動部分）、`tests/test_override.py`
