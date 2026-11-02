# 11 M1 Godot 戰鬥沙盤：選型、重用檢查、環境、施工單草案

> 文件狀態：✅ v0.2（2026-11-02，D15～D21 老闆拍板 → ADR-0014；施工單 10～15 已建檔）｜對應心智圖節點：`6. 里程碑 → M1`、`5. 技術架構 → 引擎`
> 本文是 M1 的 Stage 2 產出：T1.0 重用檢查結果、七個待拍板決策（D15～D21，附建議答案）、環境建置精靈、施工單草案。老闆拍板後寫 ADR-0014 並開施工單 10。

## 1. 先講結論（建議答案）

| # | 決策 | 建議 | 一句話理由 |
|---|---|---|---|
| D15 | Godot 版本 | **4.7.2-stable 標準版**（非 .NET） | 2026-11 最新穩定版；兩個候選骨架都是 4.7；沙盒已下載實測可無頭執行 |
| D16 | 渲染與物理 | **Compatibility（OpenGL）渲染器＋Jolt 物理** | 2018 內顯筆電目標；rts_demo 已證明 Compatibility 能跑整個 RTS；Jolt 是 4.4+ 內建 |
| D17 | 骨架 | **godot-rts-kit 當 addon 直接用**（攝影機、框選、迷霧、小地圖、格狀尋路）；rts_demo 只當參考（2D）；ccoyle95 排除（4.2、2024 停更）；huginhelm 找不到 repo | 純 GDScript 2,270 行、MIT、2026-10 仍在更新、附無頭測試與數千單位的效能基準 |
| D18 | 引擎 ↔ 戰情板 | **引擎每 100 ms 把 Board v0.2 JSON 原子寫到 `user://board.json`**；M0 的 `chief show` 直接讀；WebSocket 留 M2 | 零新依賴；Python 測試可用 M0 的 Board 模型驗證 Godot 的輸出，兩層合約不會漂 |
| D19 | 戰鬥模型與時間 | **同一份 `rules/ww2_1944.json`**；**M0 的 1 回合＝M1 的 30 秒**，10 回合＝5 分鐘會戰；傷害每秒解算，K 按 1/30 攤 | 手算例與難度劇本直接沿用；M1 一場的結果可與 M0 對照 |
| D20 | 測試 | **自寫 SceneTree 無頭測試**（`godot --headless -s tests/run_tests.gd`）＋一支 `--fixed-fps` 的 5 分鐘煙霧測試；不引入 GUT／gdUnit4 | 沙盒已實測可跑；少一個依賴 |
| D21 | 專案位置與美術 | 專案放 `ai-commander-game/godot/`（與 `m0/` 並列，D6 搬家時一起搬）；**M1 不用任何外部美術**：膠囊體＋方塊頭、方塊掩體、單色材質全部程式畫 | PRD 本來就說「無貼圖、單色材質」；Kenney 等素材留到 M3 潤飾 |

2026-11-02 老闆「好了」＝全照建議，已寫 ADR-0014。

## 2. T1.0 重用檢查（2026-11-02，沙盒實測）

| 候選 | 實測 | 判定 |
|---|---|---|
| **godot-rts-kit**（jhaney0214-sys） | MIT；Godot 4.7、Forward+（README 註明 2026-10-10 起 Compatibility 也驗過）；17 個 .gd、2,270 行；`addons/rts_kit/` 五個節點：`RTSCameraRig`、`RTSSelection`、`RTSFogOfWar`、`RTSMinimap`、`RTSNavGrid`；單位不必繼承基底類別（群組＋`rts_*` 方法契約）；`tests/run_tests.gd` 無頭測試 37 項；`BENCHMARK.md` 單機 30 fps 可跑 8,000（避障）～48,000（flow field）移動單位；最後更新 2026-10-18 | ✅ **採用**為 M1 骨架（複製 `addons/rts_kit`，不改它；我們的單位照契約實作） |
| **rts_demo**（rainwindskyfly） | MIT；Godot 4.7.2、**GL Compatibility**；24 個 .gd、4,721 行；**2D**（Node2D／CharacterBody2D）；零美術檔全程式畫；六狀態敵方 AI；`tests/smoke_test.gd` 用 `--fixed-fps 60` 跑 55 秒遊戲時間的驗收 | 🟡 **只當參考**：借「零素材」做法、煙霧測試寫法、敵方 AI 狀態機；程式不直接用（2D） |
| **godot-rts-template**（ccoyle95 Open RTS） | MIT；Godot 4.2；2024-01 後停更；117 個 .gd | ❌ 排除（版本舊、體積大） |
| **huginhelm RTS Advanced Lite** | 沙盒的 GitHub 搜尋被限制，找不到 repo；原目錄只有一個 github.io 連結 | ❌ 本輪不採用（老闆若有連結可補查） |
| Kenney Blocky Characters、UI 主題、Active Ragdoll 等 | kenney.nl、godotengine.org 在沙盒被網路白名單擋住，無法下載驗證 | ⏸ **M1 不需要**（D21：全部程式畫）；M3 潤飾再驗 |
| Godot 4.7.2 Linux 無頭版 | GitHub release 可下載（78 MB）；`--headless --version` 正常；自寫探針專案：3D 節點、Jolt、JSON、`user://` 寫檔都通 | ✅ 沙盒可跑我們自己的無頭測試（第三方專案的測試受權限限制不跑） |

授權：godot-rts-kit MIT → 進 `THIRD_PARTY.md`，保留其 LICENSE 檔。

## 3. M1 架構（引擎層怎麼接現有的中樞）

```
godot/                               Godot 4.7.2 專案（Compatibility、Jolt）
  project.godot
  addons/rts_kit/                    重用：攝影機、框選、迷霧、小地圖、格狀尋路（不改）
  scenes/Battle.tscn                 一場會戰：地圖＋部隊＋HUD
  scripts/core/rules.gd              讀 m0/rules/<era>.json（同一份表）：火力、裝甲、速度、視距、地形、天氣
  scripts/core/board.gd              Board v0.2 的 GDScript 版：每 100 ms 組 JSON、原子寫 user://board.json、事件流
  scripts/world/sector_map.gd        5×5 分區格：地形顏色、據點旗、方塊掩體；世界座標 ↔ 分區 id
  scripts/units/soldier.gd           一個方塊人：膠囊體＋方塊頭，單色依兵種；走路搖晃；死亡倒地（會戰 LOD）
  scripts/units/squad.gd             一班＝三個方塊人一組（會戰規模）；排＝三班；戰力＝存活比例
  scripts/units/formation_ai.gd      任務式命令 → 路徑與行為（seize/hold/flank/withdraw/support/reserve），移植 m0/chief/formation_ai.py
  scripts/combat/resolver.gd         每秒依 §4 公式解算同分區交戰（含迫砲鄰格、工兵、天氣時段）；K/30
  scripts/battle/director.gd         開局（讀部署好的 board JSON）、敵方劇本（回合→秒）、天氣變化、結束判定、結果畫面
  tests/run_tests.gd                 無頭單元測試（分區換算、規則查表、手算例、戰力聚合）
  tests/smoke_battle.gd              --fixed-fps 跑完 5 分鐘會戰，檢查 board.json 與結果
```

- **時間**：遊戲秒 `t`（Board `time_unit: second`）；M0 回合 n ＝ 秒 30(n−1)～30n；敵方劇本 `orders["3"]` 在第 60 秒下達。決策節拍（20 秒）與 LLM 接入是 M2 的事。
- **會戰規模**：一班三個方塊人、一排三班（9 人）、均衡範本 8 排 72 人；敵方 normal 7 排 63 人；全場 135 個 CharacterBody3D，遠低於骨架基準。
- **戰情板**：引擎是唯一寫入者；`orbat` 的排節點戰力＝存活人數比例（四捨五入到 0.01）；連＝子排平均（同 M0）；`enemy_known` 依視距（§2 v1）；事件 `kind` 與 M0 相同，讓 M0 的 `chief show`、戰報卡、回放直接可用。
- **不做**：LLM、推翻 UI、側欄、設定頁（M2）；空中支援、對決（M3）。

## 4. 環境建置精靈（Windows，老闆說「開始」才走）

| 步 | 做什麼 | 時間 | 完工判準 |
|---|---|---|---|
| 1 | 到 godotengine.org 下載 **Godot 4.7.2 標準版**（Windows 64，不是 .NET），解壓到 `C:\dev\godot\`，雙擊可開 | 5 分 | 看到專案管理員 |
| 2 | `git pull` 後在專案管理員「匯入」`C:\dev\xiaoye-legal\ai-commander-game\godot\project.godot` | 2 分 | 專案列表出現 ai-commander-game |
| 3 | 按 F5 跑 `Battle.tscn` | 1 分 | 看到 5×5 地圖與方塊人 |
| 4 | PowerShell（console 版）：`& "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/run_tests.gd; echo $LASTEXITCODE` | 1 分 | 印「checks … failures: 0」且 exit 0 |
| 5 | `uv run chief show %APPDATA%\Godot\app_userdata\ai-commander-game\board.json` | 1 分 | M0 的戰情板畫面印出 Godot 寫的板 |

## 5. 施工單草案（Stage 3 拆單；老闆拍板後正式建檔）

| # | 施工單 | 對應 | Blocked by | 30 秒驗收 |
|---|---|---|---|---|
| 10 | Godot 專案骨架＋固定俯視攝影機＋5×5 分區地圖（地形色、據點旗、方塊掩體、座標↔分區）；無頭測試跑通 | T1.1、T1.4 | — | F5 看到地圖；`run_tests.gd` 綠 |
| 11 | 方塊人、班／排／連編制樹（讀部署好的 Board JSON 生成）、編制 AI 執行六種任務（骨架尋路） | T1.2、T1.3 | 10 | 排照劇本走到 C3；戰力聚合正確 |
| 12 | 戰鬥：同分區每秒解算（§4 查表、迫砲鄰格、工兵、天氣時段）、潰散撤出、倒地；三個手算例在引擎內重現 | T1.5 | 11 | 無頭測試重現 0.1044／0.216 等值（×1/30 每秒） |
| 13 | 戰情板寫入：每 100 ms 原子寫 `user://board.json`（v0.2）、事件流、視距迷霧、歸屬；Python 端用 M0 Board 模型驗證 | T1.6 | 11 | `chief show` 讀得到、合約測試綠 |
| 14 | 一場 5 分鐘會戰：敵方劇本（回合→秒）、難度三級、天氣變化、結束與結果畫面；`--fixed-fps` 煙霧測試 | 驗收 | 12、13 | 無頭 5 分鐘打完，結果與 M0 §14 同趨勢 |
| 15 | 效能：會戰規模 60 FPS（Compatibility）；基準腳本與數字進文件；必要時 MultiMesh | T1.7 | 14 | 老闆筆電 F5 看 FPS 計數 ≥ 60 |

每張仍照規則：重用先寫明、驗收項有測試、三審、心智圖同步。

## 6. 效能實測（施工單 15，沙盒 4 核 2.1 GHz，2026-11-02；含每秒戰情板更新，剔除 tick 0）

| 規模 | 排 | 人 | 平均 ms/tick | p99 ms/tick | 最大 ms/tick |
|---|---|---|---|---|---|
| 1 倍（會戰） | 14 | 126 | 0.34 | 1.0 | 4.2 |
| 5 倍 | 70 | 630 | 1.69 | 4.4 | 10.7 |
| 10 倍（同板複製，站位重疊） | 140 | 1,260 | 3.74 | 9.1 | 15.9 |

整場實戰（含導演、尋路、每 0.1 秒寫檔）約 0.65 ms/tick。60 Hz 預算 16.7 ms；邏輯側不是瓶頸，剖析顯示移動占 75%。畫面側只能在老闆本機讀 HUD 的幀時間（ms）與 FPS（`-- stress=10` 關 V-Sync 看餘裕）；方塊人已改共用網格與材質，再不夠才上 MultiMesh。

## 7. 風險

- 沙盒沒有 GPU：畫面相關（60 FPS、迷霧外觀）只能在老闆本機驗；邏輯與合約在沙盒無頭驗。
- godot-rts-kit 的迷霧在 Compatibility 下「可用但顏色不同」（README）；M1 先接受。
- 第三方程式碼在沙盒不能執行測試（權限）；只讀碼評估，實際整合後跑我們自己的測試。
