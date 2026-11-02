# 07 參謀長包＋戰例庫回歸＋5 場驗收

**重用**：pytest（回歸）、zipfile 標準庫（打包）。自製：manifest 格式、回歸比較。

## 做什麼（老闆視角）
把參謀長裝箱：`harness/<名稱>/` 含 manifest、準則、提示、供應商設定（不含金鑰）、評測成績，可匯出 zip、匯入。每次採納準則後，自動用歷史快照重跑參謀長，算「預測推翻率」，退步超過 5 個百分點就回滾並告訴你。最後跑 M0 總驗收：同一人連打 5 場，推翻率要下降；故意塞一條壞準則，回歸要抓得到。

## Blocked by
04、06。

## 驗收清單
- [x] `uv run chief harness export default` 產生 zip；`import` 還原並驗 manifest（含路徑安全）
- [x] 戰例庫：每次推翻自動存成戰例（最新 10 筆）到 `harness/<包>/evals/cases.jsonl`；`uv run chief evals run` 印對齊率與退回率（§12）
- [x] 回歸：採納後自動回歸，退步（對齊率掉 > 5 點）自動回滾並告知；`evals run --doctrine samples/bad_doctrine.md` 可手動試
- [x] 5 場連打腳本 `uv run chief acceptance --provider ollama --battles 5`（互動）＋ `chief stats` 曲線：印每場推翻率曲線（M0 驗收：趨勢下降；若本地小模型做不到，報告如實寫並改用 Anthropic 跑一次）
- [x] 同一個參謀長包在 ollama 與 anthropic 兩個供應商都能打完一場（2026-11-02 老闆本機：Haiku 5.5 五場、qwen2.5:3b 一場，皆 0 無回應；第三家需老闆另備金鑰）
- [x] 三審（code-reviewer／test-automator／PRD 符合度）報告附在 `docs/qa/m0-review.md`（含 2026-11-02 真機驗收：首場 8.8% → 末場 4.0% 下降；壞準則 0% 退步）

## 30 秒驗收腳本
`uv run chief acceptance --provider ollama --battles 5` → 看到 5 場摘要表與推翻率曲線 → `uv run chief evals run --provider ollama` → 看到「對齊率 xx%（基準 模型 yy%，±x 點）」與退回率。

## 預估檔案
`chief/harness.py`、`chief/evals.py`、`chief/acceptance.py`、`tests/test_harness.py`、`tests/test_evals.py`、`docs/qa/m0-review.md`
