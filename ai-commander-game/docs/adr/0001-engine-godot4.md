# ADR-0001 遊戲引擎選 Godot 4
- 日期：2026-11-01
- 狀態：已採納（老闆第三輪「全照建議」）
- 背景：見 `docs/06-engine-comparison.md`（五選項比較）。本專案不要畫面、不上主機、單人開發、低硬體需求。
- 決定：M1 起使用 Godot 4（4.4 以上，內建 Jolt 物理；Compatibility 渲染器）。M0 不綁引擎，用 Python。
- 放棄的方案與原因：Unity 6（訂閱授權、編輯器對新手重；只有上主機才有必要）；Unreal 5（為 3A 畫面而生，專案體積與編譯時間過重）；純網頁 Three.js（無編輯器，保留為展示版 Plan B）；Bevy（未 1.0，每版破壞相容，AI 協作寫碼常對不上版本）。
- 後果／代價：主機平台匯出要靠第三方；3D 效能上限低於 Unity，但本專案規模階梯（ADR-0008）已把需求壓在範圍內；GDScript 與 Claude API 的接法要自己用 HTTPRequest 寫（⚠️ 社群 addon 狀態需實測）。
