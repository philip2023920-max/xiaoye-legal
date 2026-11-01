# ADR-0012 M0 技術棧：uv、Textual、LiteLLM＋instructor、anthropic SDK
- 日期：2026-11-01
- 狀態：已採納（Stage 2 選型，沙盒實測通過）
- 背景：M0 要用 Python 跑通戰情板、閘道、命令合約、推翻、AAR。候選比較見 `docs/08-stage2-architecture.md`。
- 決定：uv 管 Python 與套件；Textual 做終端機戰情板；OpenAI 相容路徑用 LiteLLM＋instructor；Anthropic 路徑用官方 SDK（strict tool、parse、快取、串流）；pydantic 共用 schema；pytest 做戰例庫回歸。版本鎖在 `m0/uv.lock`。
- 放棄的方案與原因：pip+venv／Poetry（無 lockfile／較慢多學一套）；Rich／curses（無事件處理／Windows 不可用）；全走 LiteLLM 含 Anthropic（strict tool 與快取等新功能可能落後官方 SDK）；pydantic-ai（整套 agent 框架，對 M0 過重）；自寫 adapter（重造輪子，違反 ADR-0011）。
- 後果／代價：LiteLLM 相依套件多（83 個）；instructor 與 anthropic SDK 同時存在要注意版本更新時的相容性，升版前先跑 `uv lock --upgrade` 並重跑測試。
