# 07 可重用素材與模板目錄（先找、再改、最後才自己做）

> 文件狀態：🟡 v0.1（2026-11-01）｜對應心智圖節點：`9. 素材與模板庫`｜原則見 ADR-0011
> 研究方式：WebSearch 降級研究。**每一項的授權與現況都標 ⚠️，進 Stage 2 時逐項到原始頁面驗證**，才准放進專案。
> 授權優先序：CC0 ＞ MIT／Apache ＞ CC-BY（要標註）＞ 其他（先問老闆）。

## 一句話原則

每張施工單動工前先回答：「這件事有沒有人做過、能不能直接拿、改多少？」答不出來不准從頭寫。

## 依系統分層列表

### 第 2 層：戰鬥沙盤（Godot 4）

| 用途 | 候選 | 授權 | 怎麼用 | 驗證狀態 |
|---|---|---|---|---|
| RTS 骨架：框選、下令、RTS 攝影機、戰爭迷霧、小地圖、格狀尋路 | **godot-rts-kit**（jhaney0214-sys）純 GDScript，從《Drone Command》抽出 | MIT | 直接當 M1 骨架，砍掉不需要的 | ✅ 2026-11-02 沙盒實測：Godot 4.7、2,270 行、5 個節點、無頭測試 37 項、效能基準；建議採用（D17） |
| RTS 骨架備選：含編隊、控制群組、A*、生產佇列 | **huginhelm Godot RTS Advanced Lite** | MIT（Lite）；Pro 付費 | 比較後擇一，或借編隊程式碼 | ❌ 沙盒找不到 repo（GitHub 搜尋受限）；本輪不採用 |
| 1v1 垂直切片參考：Grid A*、避障、編隊展開 | **rainwindskyfly/rts_demo**（Godot 4.7.2） | MIT | 參考編隊展開與路徑拉直的做法 | 🟡 實測：2D、GL Compatibility、零素材、`--fixed-fps` 煙霧測試；只當參考 |
| 2D 編隊與尋路演算法 | **Liech/RTSNavigationLib**（C++） | MIT | 只借演算法思路，不直接接 | ⚠️ |
| 布娃娃：主動式（受擊反應、失衡、爬行） | **Active Ragdoll**（Godot Asset Library，Godot 4.4，支援 Jolt） | MIT | 遭遇戰規模的死亡／受擊動畫 | ⚠️ |
| 布娃娃：任意人形一鍵套用 | **Drop-In Ragdoll**（Godot 4.7，Jolt）、**Auto Ragdoll**（編輯器外掛） | 免費／PWYW | 方塊人骨架自動生成 PhysicalBone | ⚠️ |
| 低多邊形地形 | **Low Poly Terrain Builder**（Godot 4.7+，可匯出 glTF） | ⚠️ 未查 | 做 3 張地圖的地形 | ⚠️ |
| 大型地形（若需要） | **Terrain3D**（TokisanGames） | MIT | 大會戰規模才需要，M3 再看 | ⚠️ |
| UI 主題 | **Kenney's UI Theme for Godot**、**Minimalistic UI Theme**、**Crisp Kit Free** | 免費／PWYW；Pixel UI Free 為 CC-BY-4.0 | 直接套，改配色 | ⚠️ |

### 美術素材（TABS 風格方塊人、低多邊形）

| 用途 | 候選 | 授權 | 怎麼用 | 驗證狀態 |
|---|---|---|---|---|
| 方塊人角色 | **Kenney Blocky Characters**（OpenGameArt 鏡像 v2.0） | CC0 | 直接當士兵基底，換配色分兵種 | ⏸ M1 不需要（D21 全部程式畫）；沙盒連不到 kenney.nl，M3 再驗 |
| 角色＋動畫 | **Kenney Character Assets**（Kay Lousberg 製作：4 模型、75 皮膚、17 動畫） | CC0 | 走路／射擊動畫來源 | ⚠️ itch 頁面曾標「暫不可下載」 |
| 其他低多邊形角色 | **KayKit Character Pack: Adventurers**（奇幻，非軍事） | CC0 | 備用 | ⚠️ |
| 低多邊形環境與載具 | **Quaternius** 各包 | ⚠️ 舊包 CC0，新包改 QAL v1.0 授權 | 逐包看授權再用 | ⚠️ 重要 |
| 軍事載具 | 待查：Kenney Car Kit／Tank、Poly Pizza 以 CC0 篩選 | — | 裝甲兵種用 | ⚠️ 未搜到確定來源 |
| 原型材質與方塊 | **Kenney Prototype Textures**（社群有 Godot 版 kenney_prototype_tools） | CC0 | 掩體、據點、地面 | ⚠️ |
| 音效 | Kenney Audio、freesound CC0 篩選 | CC0 | 射擊、腳步、UI | ⚠️ |
| 軍事單位符號（戰情板用） | **milsymbol**（JS，APP-6／MIL-STD-2525，輸出 SVG） | MIT | 預先渲染成 SVG／PNG 給 Godot 與終端機用；沒有 Python 版 | ⚠️ |

### 第 3、4 層：AI 戰情板與參謀長（Python，M0）

| 用途 | 候選 | 授權 | 怎麼用 | 驗證狀態 |
|---|---|---|---|---|
| 終端機戰情板側欄（部隊樹、事件流、表格） | **Textual**（Textualize；Tree、DataTable、Markdown 元件） | MIT | M0 的側欄直接用 Textual，不自己畫 | ⚠️ 版本 |
| 多供應商閘道（100+ 家、統一 usage） | **LiteLLM** | MIT | OpenAI 相容 adapter 直接用它；Anthropic 原生 adapter 仍自己寫以用 strict tool 與快取 | ⚠️ 需查 `completion_cost` 現行簽名 |
| 價格表（F13） | **LiteLLM `model_prices_and_context_window.json`** | MIT | 當 `prices.json` 的初始值與更新來源，玩家仍可改 | ⚠️ 聚合站數字彼此不一致，以 repo 檔案為準 |
| 結構化輸出＋驗證＋重試（含把錯誤回饋給模型） | **instructor**（Pydantic；from_openai／from_anthropic） | MIT | 命令合約 `issue_orders` 的驗證與重試直接用 | ⚠️ `max_retries` 參數需查 |
| 「LLM 指揮 RTS」的提示與摘要方法 | **TextStarCraft II**（NeurIPS 2024；Chain of Summarization：單幀摘要＋多幀摘要；微操交給規則腳本） | ⚠️ 研究用 repo，授權未查 | 借「摘要鏈」設計與提示寫法；不接程式（Windows + SC2 限定） | ⚠️ |
| 本地模型 | **Ollama** | MIT | D9 已拍板 | — |

### 第 5 層與工具

| 用途 | 候選 | 授權 | 怎麼用 | 驗證狀態 |
|---|---|---|---|---|
| 心智圖 | **markmap** | MIT | 已在用 | ✅ |
| 多語字串 | Godot 內建 `TranslationServer`＋CSV | — | 不另找 | — |
| 戰例庫回歸的測試骨架 | pytest | MIT | 直接用 | — |

## 老闆看得懂的用法

- 每張施工單的第一行會寫「**重用**：XXX（授權）」或「**自製，因為**：找過 A、B 都不合」。
- 專案內建 `THIRD_PARTY.md`，列出每個拿進來的東西、授權、改了什麼。CC-BY 的要放署名。
- 不碰授權不明或「個人非商用」的素材；Quaternius 新授權（QAL）要先看條文。

## 來源

- RTS 骨架：https://github.com/jhaney0214-sys/godot-rts-kit 、https://openclawaimac.github.io/ 、https://github.com/rainwindskyfly/rts_demo 、https://github.com/ccoyle95/godot-rts-template 、https://github.com/Liech/RTSNavigationLib
- 布娃娃與地形：https://godotengine.org/asset-library/asset/5575 、https://forum.godotengine.org/t/drop-in-ragdoll-a-ragdoll-for-any-humanoid-at-any-scale-free/145751 、https://store.godotengine.org/asset/manik/auto-ragdoll/ 、https://store.godotengine.org/asset/fabians/low-poly-terrain-builder/ 、https://github.com/TokisanGames/Terrain3D
- UI 主題：https://azagaya.itch.io/kenneys-ui-theme 、https://azagaya.itch.io/minimalistic-ui 、https://godotengine.org/asset-library/asset/5494
- 美術：https://opengameart.org/content/blocky-characters 、https://kenney.itch.io/kenney-character-assets 、https://gameworldobserver.com/2023/01/20/free-game-assets-tutorials-quaternius-indie-developers 、https://github.com/GeroVeni/kenney_prototype_tools
- 符號：https://github.com/spatialillusions/milsymbol/
- Python：https://blog.brightcoding.dev/2026/07/11/textual-the-revolutionary-framework-for-terminal-uis 、https://dev.to/binyam/cost-tracking-and-model-spend-monitoring-with-litellm-4io2 、https://github.com/jxnl/instructor/blob/main/README.md 、https://pypi.org/project/litellm-cost-tracker/
- TextStarCraft II：https://proceedings.neurips.cc/paper_files/paper/2024/hash/f0ebc318e2df08360b2df559e81602e5-Abstract.html 、https://arxiv.org/html/2312.11865v1
- DeepSeek 價格（聚合站，需核對）：https://cloudprice.net/models/deepseek/deepseek-chat
