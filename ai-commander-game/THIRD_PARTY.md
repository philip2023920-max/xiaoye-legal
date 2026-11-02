# 第三方元件清單（ADR-0011 重用優先）

每個拿進專案的東西都列在這裡：用途、授權、改了什麼。授權以安裝後的 METADATA 或原始 repo 為準。

## M0（Python）— 2026-11-01 沙盒實測安裝

| 套件 | 版本 | 授權 | 用途 | 改動 |
|---|---|---|---|---|
| textual | 8.2.8 | MIT | 終端機戰情板 | 無 |
| rich | 14.3.4 | MIT | Textual 相依 | 無 |
| litellm | 1.106.6 | MIT | OpenAI 相容閘道、價格表 | 無 |
| openai | 2.54.0 | Apache-2.0 | LiteLLM／instructor 相依 | 無 |
| instructor | 1.17.0 | MIT | 結構化輸出驗證與重試 | 無 |
| anthropic | 2.3.0 | Apache-2.0 | Anthropic 原生 adapter | 無 |
| pydantic | 2.14.2 | MIT | schema | 無 |
| python-dotenv | 1.2.4 | BSD-3-Clause | 讀 .env | 無 |
| pytest | 9.2.0 | MIT | 測試 | 無 |
| uv | — | MIT／Apache-2.0 | 套件管理 | 無 |

## 工具

| 元件 | 授權 | 用途 |
|---|---|---|
| markmap-autoloader 0.18.12 | MIT | mindmap.html |

## M1（Godot）— 待 Stage 2 for M1 驗證後填入

候選見 `docs/07-reuse-catalog.md`。

## M1（Godot）— 2026-11-02 T1.0 重用檢查（D17 拍板，`godot/addons/rts_kit` 已複製，含 LICENSE）

| 元件 | 版本 | 授權 | 用途 | 改動 |
|---|---|---|---|---|
| Godot Engine | 4.7.2-stable | MIT | 戰鬥沙盤引擎 | 無 |
| godot-rts-kit（jhaney0214-sys，`addons/rts_kit`） | 2026-10-18 commit | MIT | 攝影機、框選、迷霧、小地圖、格狀尋路 | 不改；保留 LICENSE |
