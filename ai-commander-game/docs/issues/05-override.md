# 05 總司令推翻與接管（終端機）

**重用**：Textual 8（互動式畫面：部隊樹、命令清單、按鍵）。自製：推翻紀錄與後果判定。

## 做什麼（老闆視角）
把自動打改成「參謀長先下令，老闆看一眼再放行」：每回合畫面列出參謀長的命令，按 Enter 全部採納；或選一條改掉（選單位 → 選任務 → 選目標），該單位就變成「總司令直轄」，參謀長之後不再對它下令，直到老闆放手。每次推翻都記下：AI 原令、你的令、當時沙盤、下一回合後果 👍👎➖。

## Blocked by
03（可與 04 並行）。

## 驗收清單
- [ ] `uv run chief play --provider ollama`（不加 `--auto`）進入互動模式，每回合可 Enter 採納或改令
- [ ] 改令後戰情板該單位 `controlled_by: player`，下一回合參謀長的命令不含該單位（驗證器擋下並記錄）
- [ ] 「放手」操作讓單位回到 `ai`
- [ ] 推翻紀錄寫入 `battles/<id>/overrides.jsonl`，欄位：turn、unit、ai_order、player_order、snapshot_ref、outcome
- [ ] 後果判定：下一回合該單位戰力與所在據點變化 → 👍／👎／➖，規則與手算例子寫在 `docs/10-sim-rules.md`
- [ ] 戰後印「推翻率：n/m」

## 30 秒驗收腳本
`uv run chief play --provider ollama` → 第 1 回合選一條命令改成「hold」→ 看到該單位標記為直轄 → 第 2 回合參謀長沒再對它下令 → 戰後印推翻率。

## 預估檔案
`chief/tui.py`、`chief/override.py`、`tests/test_override.py`
