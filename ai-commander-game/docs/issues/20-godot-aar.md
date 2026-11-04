# 20 戰後 AAR 畫面：戰報卡、討論、採納

> 狀態：✅ 2026-11-04 結案：三審兩輪（11＋2 項）全部修正，`tests/test_aar.gd` 37 檢查（含真的啟動 chief serve 走完卡 → 一句話 → 討論 → 提案 → 採納 → 撤銷）。ADR-0015；規則 docs/10 §11、§12、§16。

**重用**：16 的 `/battle/end`、`/aar/line`／`discuss`／`propose`／`adopt`／`skip`／`undo`（卡、徽章、討論、diff、採納、回歸、撤銷、aar.json 全在服務端）；18 的字串表。自製：`scripts/ui/aar_screen.gd`（`AarScreen`：`render(model)` 把整個狀態畫出來、按鈕只發訊號；純函式 `header_text`／`badge_names`／`moments_bbcode`／`diff_bbcode`／`transcript_bbcode`）、`battle.gd` 的 `_show_aar`／`aar_line`／`aar_discuss`／`aar_propose`／`aar_adopt`／`aar_skip`／`aar_undo`（服務呼叫、`aar_model`）；字串表 +44 鍵（含五個徽章名）。

## 驗收清單
- [x] 會戰結束（`/battle/end` 回 200）→ 左 60% 的面板（側欄留在右邊）：勝負與星數（★★★／★★☆／★☆☆）、秒數與結束原因、據點、推翻次數與率、未判定數、費用、供應商／模型、徽章（五個 id → 三語名稱）、關鍵三幕（推翻 👍綠 👎紅 ➖灰、轉折）、提示、參謀長一句話（`/aar/line` 自動呼叫）
- [x] 討論：三個快速回覆按鈕（每回合不同，服務給）＋輸入框（Enter 送出），最多三回合（第 4 回合起沒有按鈕與輸入框），對話串顯示；隨時可「提出準則修改」或「跳過」
- [x] 提案：摘要、新增（綠）、刪除（紅）、空提案顯示「沒有變更」且不能採納；「採納」→ 服務套用＋回歸（訊息逐條顯示；退步自動回滾顯示「回歸退步，已自動回滾」）→「撤銷」→「已還原上一版準則」；aar.json 由服務寫；等回覆時按鈕全停並顯示「參謀長思考中…」；服務錯誤以人話顯示在畫面、不改階段
- [x] 流程計時「戰後 n 秒（目標 < 120）」每 0.5 秒更新、超過變紅；「再打一場」＝R 重開（先關服務、重載場景）
- [x] 無頭測試 `tests/test_aar.gd`（37 檢查）：純函式 9 項（含 bbcode 跳脫）；render 各階段按鈕可見性／停用／Enter 不重送／回滾無撤銷／服務時間優先／按鈕列在提案下 18 項；真的啟動 chief serve（fake、`--harness none --doctrine battles/aar_test/doctrine.md`，不碰 harness/default）→ 第 1 拍 → 推翻 → 提早結束 → 卡（推翻 1、未判定 1）→ 一句話自動到 → 快速回覆 1 → 輸入 → 提案（demo）→ 採納（準則檔真的變）→ 撤銷（還原）→ 計時

## 30 秒驗收腳本
```powershell
cd godot; & "C:\dev\godot\Godot_v4.7.2-stable_win64_console.exe" --headless --path . -s tests/test_aar.gd; echo $LASTEXITCODE
```
`checks: 37 (expected 37), failures: 0`。然後 F5 打完一場（或等戰力低於 30%）→ 卡出現、幾秒內參謀長的一句話到 → 按一個快速回覆 → 按「提出準則修改」→ 按「採納」→ `m0/harness/default/doctrine.md` 多了條目（`chief doctrine show`）；「撤銷」還原。

## 施工備註
- 服務的 `/battle/end` 用 pydantic 驗 `result`：導演提早結束時 `end_reason` 一定要是 turns／strength（`_finish()` 自己不設原因，由 `_on_second` 設；測試直接呼叫時要先設）。
- 畫面不碰任何檔案：採納與撤銷都在服務端改 `doctrine.md`／`doctrine.prev.md`；Godot 只拿回應顯示。

## 三審第一輪（2026-11-04，code-reviewer 軸）→ 3 必修＋8 建議全部修正
- 必修：busy 鎖擋不住 Enter（手快一次吃掉兩回合、第 4 回合顯示 null）→ `_aar_call` 重入守門、busy 時輸入框 `editable=false`、`_send` 看 `send_btn.disabled`、服務回 `reply=null` 不追加對話；M1 結果標籤疊在卡上 → 卡出現時收起（服務失敗時留著當保底）、面板改不透明底；對話／diff／三幕的 bbcode 沒跳脫 → 全形方括號（與側欄同）。
- 建議：en 的三顆快速回覆撐破面板 → `HFlowContainer`；計時器只在開側欄時走 → 移出；自動回滾後仍顯示「撤銷」→ `and not rolled_back`、撤銷訊息追加不覆蓋；戰後點側欄仍開推翻面板 → `select_unit` 在卡開著時不選；按鈕列移到提案下面；四句硬編中文進字串表；採納後改顯示服務記的 `duration_s`（與 `chief stats` 一致）；`/aar/line` 失敗顯示「（參謀長沒有回話）」；測試開頭清掉上次的 out 資料夾。

## 三審第二輪（驗證）→ 可結案；順手修 2 小項
- 戰後計時器仍以側欄的計時變數當閘（側欄關掉就不動）→ 0.5 秒節拍獨立於側欄；服務失敗訊息帶原始路徑 → 「參謀長服務回錯：原因」。
