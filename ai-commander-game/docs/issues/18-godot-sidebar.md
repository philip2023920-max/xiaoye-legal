# 18 戰情板側欄 UI

> 狀態：🟡 程式完成（2026-11-04）；三審兩輪（第一輪 14 項：12 修＋2 延到 21；第二輪 4 補強＋5 小項）已修，`tests/test_sidebar.gd` 44 檢查全過，待確認。決策 D26（內建 Control）、D27（三語字串表）見 docs/12 §1（ADR-0015 採納）。

**重用**：Godot `Tree`、`RichTextLabel`、`PanelContainer`、`TranslationServer`；M1 的 `BoardWriter.to_dict()`（側欄讀同一份字典，不另造資料）；骨架 `RTSCameraRig.look_at_ground`。自製：`scripts/ui/sidebar.gd`（`Sidebar`）、`scripts/ui/i18n.gd`（`UiText`：執行期把 `i18n/ui.csv` 載進 TranslationServer，不用 Godot 的 CSV 匯入器、不產二進位 .translation）、`i18n/ui.csv`（三語一次齊；19 之後 60 鍵）。

## 驗收清單
- [x] 右側欄（可收合，按鈕切換）：部隊樹（連→排：名稱、5 格戰力條＋數字、狀態、任務、★直轄標記；直轄黃、潰散／殲滅紅；殲滅的排板上留著紅字，真的從板上消失才移除、既有列不重建）、事件流（最近 12 筆舊→新；推翻後果 👍綠 👎紅 ➖灰、參謀長令黃、易手／接觸藍、潰散／殲滅紅、天氣紫）、參謀長區（狀態／最近研判／思考中 n 秒／最近一拍放行的命令）、據點與分數（✔✘）、天氣時段與剩餘秒數、本場費用與拍數
- [x] 每 0.5 秒（`_process`）從 `BoardWriter.to_dict()`＋`Battle.chief_sidebar_info()` 更新；點樹上的排或連 → `unit_selected` → 攝影機 `look_at_ground`（排＝錨點、連＝存活下級排平均）；`Sidebar.selected_unit` 留給 19
- [x] 側欄字串全部走 `i18n/ui.csv`（zh_TW／zh_CN／en 三欄一次齊，測試驗每個鍵三語都有）；`UiText.set_lang(chief_lang)` 讓 UI 與參謀長同語言；命令列 `-- lang=en`。HUD 第一、二行與事件文字留給 21
- [x] 無頭測試 `tests/test_sidebar.gd`（44 檢查，1280×720 真視窗量版面）：版面（最小高 ≤ 720、欄寬、焦點、收合保留、排先於連、連消失）、HUD 換行；字串表三語與 CSV 引號；`tree_rows`／戰力條／任務狀態文字／事件上色／最近 12 筆／據點分數／天氣時段／參謀長區；節點建樹、更新、直轄與潰散上色、殲滅移除、選取訊號、收合展開；Battle 場景裡的側欄開局建好、40 秒後跟著板、點 A1 排攝影機移過去

## 30 秒驗收腳本
```powershell
cd godot; & "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/test_sidebar.gd; echo $LASTEXITCODE
```
`checks: 44 (expected 44), failures: 0`。然後 F5 → 右側看到部隊樹與事件流即時跳動；點「A3 步兵排」攝影機跳過去；右上「收合側欄 ▶」收起。

## 三審第一輪（2026-11-04，code-reviewer 軸，無頭探針量 1280×720 版面）→ 14 項：12 修、2 延到 21
- 高：側欄最小高 767～949 裝不進 720（費用、天氣在螢幕外）→ `ScrollContainer` 包內容、樹／事件最小高 140／120；名稱欄只剩 60 px、「★直轄」被截 → 寬 340 → 440、欄 1～3 固定寬、名稱欄 expand＋clip。
- 中：側欄蓋住 HUD 兩行右端 239 px → HUD 兩行 autowrap、寬＝視窗 − 側欄 − 邊距、第二行下移；捲軸落在攝影機邊緣捲動區 → 滑鼠在側欄／面板上時 `edge_scroll_enabled=false`；點樹／按鈕後焦點吃掉空白鍵 → 樹、按鈕、事件流、面板按鈕全部 `FOCUS_NONE`；repo 多了匯入器產物（`ui.csv.import` csv_translation＋3 個二進位 .translation）→ `importer="keep"`、刪檔、`.gitignore`。
- 低：連消失時子排 TreeItem 懸空 → `is_instance_valid` 守門、兩趟建樹（先連再排，不靠板順序）；每次 refresh 展開連 → 只在建立時；300 秒寫死兩份 → Battle 傳 `Director` 常數；`task_text` 未知任務漏鍵名 → 保底；文件偏差（鍵數、ADR 引用、「殲滅移除」措辭）。
- 留給 21：切語言不會重翻 `_init` 時翻好的靜態字串（設定頁改語言要重建側欄或改用自動翻譯）；事件流 `scroll_following` 讓使用者翻不了舊事件。

## 三審第二輪 → 4 補強＋5 小項全部修正
- 補強：釋放守門是死碼（標型別的賦值遇到已釋放的項直接拋錯）→ 不標型別＋`is_instance_valid`，補「連＋子排同時消失」測試；收合後側欄仍是 73×720 整條（右邊點不到、邊緣捲動永遠失效）→ 收合時 `anchor_bottom=0` 只剩按鈕；HUD 寬只在建立時算一次（縮到 1024 又蓋住側欄）→ `size_changed` 重算；樹只有 140 px → 樹 `EXPAND_FILL` 比例 2、最小 200，參謀長區最多 5 行、最近命令同一行、據點同一行、天氣與費用合併一行，M2 常態（研判兩行＋三條命令）內容裝進捲動區（測試實量）。
- 小項：第二行 y 依狀態行實際高度推；邊緣捲動加玩家層級開關（21 用）；測試改在 1280×720 量（HUD 寬 816、縮到 1024 → 560、側欄 (840,0,440,720)、收合矩形）；`_status_text` 用 `battle_seconds()`；文件措辭。真機請看一眼 █／★／👍 字形是否顯示（無頭容器沒有系統字型）。
