# 18 戰情板側欄 UI

> 狀態：🟡 程式完成（2026-11-04；`tests/test_sidebar.gd` 31 檢查全過；chief client 35、smoke 24、run_tests 32 不受影響），審查中。ADR-0015（D26、D27）。

**重用**：Godot `Tree`、`RichTextLabel`、`PanelContainer`、`TranslationServer`；M1 的 `BoardWriter.to_dict()`（側欄讀同一份字典，不另造資料）；骨架 `RTSCameraRig.look_at_ground`。自製：`scripts/ui/sidebar.gd`（`Sidebar`）、`scripts/ui/i18n.gd`（`UiText`：執行期把 `i18n/ui.csv` 載進 TranslationServer，不用 Godot 的 CSV 匯入器、不產二進位 .translation）、`i18n/ui.csv`（46 鍵三語）。

## 驗收清單
- [x] 右側欄（可收合，按鈕切換）：部隊樹（連→排：名稱、5 格戰力條＋數字、狀態、任務、★直轄標記；直轄黃、潰散／殲滅紅；殲滅後從板上消失就移除、既有列不重建）、事件流（最近 12 筆舊→新；推翻後果 👍綠 👎紅 ➖灰、參謀長令黃、易手／接觸藍、潰散／殲滅紅、天氣紫）、參謀長區（狀態／最近研判／思考中 n 秒／最近一拍放行的命令）、據點與分數（✔✘）、天氣時段與剩餘秒數、本場費用與拍數
- [x] 每 0.5 秒（`_process`）從 `BoardWriter.to_dict()`＋`Battle.chief_sidebar_info()` 更新；點樹上的排或連 → `unit_selected` → 攝影機 `look_at_ground`（排＝錨點、連＝存活下級排平均）；`Sidebar.selected_unit` 留給 19
- [x] 側欄字串全部走 `i18n/ui.csv`（zh_TW／zh_CN／en 三欄一次齊，測試驗每個鍵三語都有）；`UiText.set_lang(chief_lang)` 讓 UI 與參謀長同語言；命令列 `-- lang=en`。HUD 第一、二行與事件文字留給 21
- [x] 無頭測試 `tests/test_sidebar.gd`（31 檢查）：字串表三語與 CSV 引號；`tree_rows`／戰力條／任務狀態文字／事件上色／最近 12 筆／據點分數／天氣時段／參謀長區；節點建樹、更新、直轄與潰散上色、殲滅移除、選取訊號、收合展開；Battle 場景裡的側欄開局建好、40 秒後跟著板、點 A1 排攝影機移過去

## 30 秒驗收腳本
```powershell
cd godot; & "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/test_sidebar.gd; echo $LASTEXITCODE
```
`checks: 31 (expected 31), failures: 0`。然後 F5 → 右側看到部隊樹與事件流即時跳動；點「A3 步兵排」攝影機跳過去；右上「收合側欄 ▶」收起。
