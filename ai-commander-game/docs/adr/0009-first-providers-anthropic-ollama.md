# ADR-0009 首批供應商：Anthropic 原生＋Ollama 本地
- 日期：2026-11-01
- 狀態：已採納（老闆第三輪「全照建議」）
- 背景：LLM 閘道要支援多家（ADR-0003），M0 需要先挑兩條路徑把介面定下來。
- 決定：M0 同時實作 Anthropic 原生 adapter（Messages API、strict tool、prompt caching、串流）與 OpenAI 相容 adapter（先以 Ollama 本地模型驗證；同一 adapter 日後直接套 OpenAI、Gemini 相容端點、LM Studio、vLLM、OpenRouter、DeepSeek）。
- 放棄的方案與原因：只做 Anthropic（閘道介面會被單一供應商形狀綁死）；先做 OpenAI 雲端（要花錢，Ollama 可零成本測）。
- 後果／代價：Ollama 的結構化輸出不保證，驗證器與重試在 M0 就要做好；供應商能力表 `provider.json` 從 M0 起維護；老闆本機需安裝 Ollama 並拉一個小模型（⚠️ 進 Stage 2 時列入環境建置）。
