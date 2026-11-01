# 07 參謀長包＋戰例庫回歸＋5 場驗收

**重用**：pytest（回歸）、zipfile 標準庫（打包）。自製：manifest 格式、回歸比較。

## 做什麼（老闆視角）
把參謀長裝箱：`harness/<名稱>/` 含 manifest、準則、提示、供應商設定（不含金鑰）、評測成績，可匯出 zip、匯入。每次採納準則後，自動用歷史快照重跑參謀長，算「預測推翻率」，退步超過 5 個百分點就回滾並告訴你。最後跑 M0 總驗收：同一人連打 5 場，推翻率要下降；故意塞一條壞準則，回歸要抓得到。

## Blocked by
04、06。

## 驗收清單
- [ ] `uv run chief harness export default` 產生 zip；`import` 還原並驗 manifest
- [ ] 戰例庫：每場自動存 10 個快照到 `evals/`；`uv run chief evals run` 印預測推翻率
- [ ] 回歸：塞入 `samples/bad_doctrine.md` 後 `evals run` 判定退步並回滾，事件流有紀錄
- [ ] 5 場連打腳本 `uv run chief acceptance --provider ollama`：印每場推翻率曲線（M0 驗收：趨勢下降；若本地小模型做不到，報告如實寫並改用 Anthropic 跑一次）
- [ ] 同一個參謀長包在 ollama 與 anthropic 兩個供應商都能打完一場
- [ ] 三審（code-reviewer／test-automator／PRD 符合度）報告附在 `docs/qa/m0-review.md`

## 30 秒驗收腳本
`uv run chief acceptance --provider ollama` → 看到 5 場摘要表與推翻率曲線 → `uv run chief evals run` → 看到「預測推翻率 xx%，與上版相比 ±x」。

## 預估檔案
`chief/harness.py`、`chief/evals.py`、`chief/acceptance.py`、`tests/test_harness.py`、`tests/test_evals.py`、`docs/qa/m0-review.md`
