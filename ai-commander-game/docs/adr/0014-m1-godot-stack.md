# ADR-0014 M1 技術棧：Godot 4.7.2、Compatibility＋Jolt、godot-rts-kit 骨架、戰情板寫檔、同一份規則表
- 日期：2026-11-02
- 狀態：已採納（老闆「好了」＝全照建議，D15～D21）
- 背景：M0 已驗證成長迴圈（施工單 01～09）。M1 要把文字沙盤換成 Godot 3D 戰鬥沙盤，不碰 LLM（M2）。選型細節與重用檢查見 `docs/11-m1-architecture.md`。
- 決定：
  1. Godot **4.7.2-stable 標準版**；專案放 `ai-commander-game/godot/`。
  2. **Compatibility（OpenGL）渲染器＋Jolt 物理**；目標 2018 內顯筆電 60 FPS（會戰規模）。
  3. **godot-rts-kit**（MIT）整個 `addons/rts_kit` 複製進專案、不改；單位照它的群組與 `rts_*` 契約實作。rts_demo 只當參考（2D）。
  4. 引擎是戰情板唯一寫入者：**每 100 ms 原子寫 `user://board.json`（Board v0.2）**；M0 的 Python 讀同一份；WebSocket 留 M2。
  5. **同一份 `m0/rules/<era>.json`**；時間對應 **M0 一回合＝30 秒**，10 回合＝5 分鐘；傷害每秒解算、K 按 1/30 攤。手算例與難度劇本沿用。
  6. 測試：自寫 SceneTree 無頭測試＋`--fixed-fps` 五分鐘煙霧測試；沙盒可跑（已實測）；不引入 GUT／gdUnit4。
  7. M1 不用外部美術：膠囊體＋方塊頭、方塊掩體、單色材質全程式畫；Kenney 等素材 M3 再驗。
- 放棄的方案與原因：Forward+（內顯筆電吃力）；huginhelm Lite（沙盒找不到 repo）；ccoyle95 模板（Godot 4.2、停更）；把規則重寫一份在 GDScript（兩份真相會漂）；WebSocket 先做（M1 沒有 LLM，寫檔就夠且可被 M0 測試驗證）。
- 後果／代價：畫面與 FPS 只能在老闆本機驗；迷霧在 Compatibility 下外觀略不同；匯出時規則表要複製進專案（M1 開發期直接讀 `../m0/rules`）。
