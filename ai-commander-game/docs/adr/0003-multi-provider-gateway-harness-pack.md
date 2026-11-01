# ADR-0003 LLM 閘道支援多家供應商，參謀長可打包對決
- 日期：2026-11-01
- 狀態：已採納（老闆第一輪拍板）
- 背景：見 `docs/05-decisions.md` 第一輪
- 決定：建立 LLM 閘道層：Anthropic 原生 adapter＋OpenAI 相容 adapter（OpenAI、Gemini、Ollama、LM Studio、vLLM、OpenRouter 等）。參謀長的準則、提示、供應商設定打包成「參謀長包」，可匯出匯入、本地對決；老闆釋出官方挑戰包。
- 放棄的方案與原因：只接 Anthropic（最省事，但違背老闆要本地對決與開放生態的目標）。
- 後果／代價：結構化輸出品質各家參差，客戶端驗證器成為必備；提示模板要寫得供應商中立；多一層抽象，M0 就要定義閘道介面。
