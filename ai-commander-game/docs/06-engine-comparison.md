# 06 引擎選項比較（D1 用）

> 文件狀態：❓ 等老闆拍板（2026-11-01）｜對應心智圖節點：`4. 技術架構 → 引擎`
> 研究方式：deer-flow 不可用，WebSearch 降級研究；授權數字來自第三方整理，⚠️ 正式簽約前請老闆看官方頁面。

## 先講結論

針對本專案的四個硬條件：**單人開發、低硬體需求、數百到數千單位、要呼叫外部 LLM API**，建議順位是：

1. **Godot 4**（首選）
2. **Unity 6**（若老闆想要最大教學資源與資產商店）
3. **純網頁 Three.js／Babylon.js**（若老闆想要「給朋友一個網址就能玩」勝過一切）
4. Unreal 5 與 Bevy 不建議（理由見下）

## 五個選項逐一比較

| 項目 | Godot 4 | Unity 6 | Unreal 5 | 純網頁（Three.js / Babylon.js） | Bevy（Rust） |
|---|---|---|---|---|---|
| 授權費 | MIT，永遠免費、無分成 | 按席位訂閱；年收 < US$200K 免費，之後 Plus 約 $399／年、Pro 約 $2,040～2,310／年（來源數字不一致 ⚠️） | 免費到產品累積營收 US$100 萬，之後抽 5%（Epic 商店 3.5%） | 免費（MIT） | 免費（MIT/Apache） |
| 學習曲線（新手） | 低。GDScript 像 Python；編輯器輕 | 中。C# 必學；編輯器功能多 | 高。C++ 或藍圖；專案動輒數十 GB | 中。要自己拼：渲染、物理、UI 各找一套 | 高。Rust 本身就是門檻；0.x 版每版都破壞相容 |
| 低硬體需求 | ✅ 有 Compatibility（OpenGL）渲染器 | ✅ 可以，但預設管線偏重 | ❌ 引擎本身就吃硬體 | ✅ 瀏覽器就能跑 | ✅ |
| 數百～數千單位 | ✅ 官方文件：MultiMesh 處理「數千」夠用；社群有人用 C# 跑 5,000 個 3D 士兵 | ✅ DOTS/ECS 專為大量單位設計，但學習成本高 | ✅ 能力最強，但殺雞用牛刀 | 🟡 要自己做 instancing，可行但費工 | ✅ ECS 天生適合，但工具鏈不成熟 |
| 呼叫 LLM API | ✅ 內建 HTTPRequest；社群有 Claude addon 與 OpenAI 相容 client | ✅ UnityWebRequest；第三方套件多 | ✅ 可以，較繁瑣 | ✅ 最簡單，fetch 一行 | 🟡 用 Rust HTTP 套件，可行 |
| 3D 物理（TABS 風格） | ✅ Jolt 物理（4.4 起內建）；ragdoll 有官方文件 | ✅ PhysX，成熟 | ✅ Chaos，最強 | 🟡 Rapier／Ammo，要自己接 | 🟡 bevy_rapier |
| 匯出平台 | PC／Mac／Linux／Web／手機；主機要第三方 | 全平台含主機 | 全平台含主機 | 只有瀏覽器（可用 Electron 包） | PC／Web |
| AI 協作寫程式的友善度 | 高。GDScript 文件完整、程式碼短 | 高。C# 範例最多 | 中 | 高。JS 範例最多 | 低。API 常變，AI 寫出來的常是舊版 |
| 社群與教學 | 快速成長，但 3D RTS 教學少 | 最多 | 多但偏 3A | 多但零散 | 少 |

## 各選項的「致命傷」一句話

- **Godot 4**：3D 效能不如 Unity／Unreal，主機平台靠第三方。對本專案（低多邊形、不上主機）**都不是問題**。
- **Unity 6**：2023 年 Runtime Fee 風波已撤回，但政策反覆的記憶還在；對新手來說編輯器太重。
- **Unreal 5**：為 3A 畫面而生，本專案刻意不要畫面；專案體積與編譯時間會吃掉老闆的耐心。
- **純網頁**：沒有編輯器，地圖、單位、UI 全部用程式碼拼；多人協作難。但「一個網址就能玩」對早期推廣極有價值，建議保留為 **Plan B 或展示版**。
- **Bevy**：還沒 1.0，官方明講每版都會破壞相容；AI 協作寫出來的程式碼常對不上版本。**排除**。

## 建議的拍板方式

老闆只要回答一個問題：**「要不要主機平台（Switch／PS）？」**
- 不要 → Godot 4，沒有懸念。
- 要 → Unity 6（Godot 主機匯出靠第三方公司，多一層不確定）。

另外建議：M0 文字版沙盤與 AI 戰情板用 **Python** 寫（不綁引擎），M1 再進引擎。這樣引擎決定可以延後到 M0 驗證完。

## 來源

- 授權比較：https://blog.promise.legal/game-engine-license-agreements-unreal-unity-godot/ 、https://dev.to/oceanviewgames/which-game-engine-should-you-use-unity-vs-unreal-vs-godot-2026-4ndj 、https://phantomcave.com/blog/best-game-development-engines/ 、https://generalistprogrammer.com/tutorials/game-development-engines-2025
- Godot MultiMesh 官方文件：https://docs.godotengine.org/en/4.2/classes/class_multimesh.html ；社群 5,000 士兵實測：https://forum.godotengine.org/t/2-5d-europe-working-title-medieval-england-rts-from-2-5d-sprites-to-full-3d-in-godot-4-c/145737
- Bevy 狀態：https://bevy.org/news/ 、https://www.strayspark.studio/blog/bevy-rust-game-engine-2026-indie-guide
- Godot vs Unity 2026：https://tech-insider.org/godot-vs-unity-2026/ 、https://oceanviewgames.co.uk/blog/posts/unity-vs-godot-vs-unreal-2026
