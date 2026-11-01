# CHIEF M0 — 文字版沙盤與 AI 戰情板（Python）

> 狀態：Stage 2 環境建置中。程式碼在 Stage 3 才動工，這裡只有環境骨架。

## 快速開始（細節見 `../docs/08-stage2-architecture.md` 的環境建置精靈）

```bash
uv sync
cp .env.example .env
bash tools/capture_keys.sh            # Windows: powershell -ExecutionPolicy Bypass -File tools\capture_keys.ps1
uv run python -m chief.doctor
```

## 技術棧（ADR-0012，全部鎖版本於 `uv.lock`）

| 用途 | 套件 | 版本 | 授權 |
|---|---|---|---|
| 套件與 Python 管理 | uv | 最新 | MIT／Apache-2.0 |
| 終端機戰情板 | textual | 8.2.8 | MIT |
| OpenAI 相容閘道＋價格表 | litellm | 1.106.6 | MIT |
| 結構化輸出驗證與重試 | instructor | 1.17.0 | MIT |
| Anthropic 原生 adapter | anthropic | 2.3.0 | Apache-2.0 |
| 資料模型 | pydantic | 2.14.2 | MIT |
| 讀 .env | python-dotenv | 1.2.4 | BSD-3 |
| 測試 | pytest | 9.2.0 | MIT |

授權以安裝後 METADATA 為準（見 `../THIRD_PARTY.md`）。
