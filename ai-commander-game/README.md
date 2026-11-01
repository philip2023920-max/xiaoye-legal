# AI 參謀長 RTS（專案代號 CHIEF）

> 玩家是總司令，AI 是會越打越懂你的參謀長。畫面走 TABS 風格的簡化低多邊形，重點在「參謀長成長迴圈」。
> 目前階段：**Stage 1 需求釐清**，等老闆拍板 `docs/05-decisions.md` 的 D1～D7。

## 心智圖就是施工藍圖

`MINDMAP.md` 是本專案唯一的「總圖」，`mindmap.html` 是它的可視化（由腳本產生，**不要手改 html**）。

```
MINDMAP.md（老闆編輯）──sync_mindmap.py──▶ mindmap.html（瀏覽器打開看）
     │
     └── 每個節點 → docs/*.md（細節說明書）
```

### 老闆怎麼改

1. 用任何文字編輯器打開 `MINDMAP.md`
2. 想加功能就加一行 `- 新功能名稱 ⬜`；想叫 Claude 做就把 `⬜` 改成 `🟡`；想砍掉就改 `❌`
3. 想改決策就去 `docs/05-decisions.md` 回答題號，或在心智圖節點旁直接寫「老闆：選 Unity」
4. 存檔，告訴 Claude：「照心智圖做」

### Claude 怎麼做（每次更動的固定流程）

1. 先讀 `MINDMAP.md`，找出所有 🟡 節點與老闆新增的備註
2. 只做 🟡 的事；⬜ 不碰、❌ 不做、❓ 先問
3. 做完把節點改 ✅，必要時更新對應的 `docs/*.md`
4. 執行 `python tools/sync_mindmap.py`，重新產生 `mindmap.html`，並檢查索引中的檔案都存在
5. 在 `CHANGELOG.md` 加一條：日期｜動了哪些節點｜改了哪些檔
6. 階段切換（Stage 1→2→3→4）必須老闆明說，Claude 不自己往下跳

### 狀態符號

| 符號 | 意思 |
|---|---|
| ⬜ | 未開始 |
| 🟡 | 老闆要 Claude 這次做 |
| ✅ | 完成 |
| ❌ | 作廢／本版不做 |
| ❓ | 等老闆決策 |

## 看心智圖

- 本機：雙擊 `mindmap.html`（需要網路，載入 markmap 程式庫；版號 `markmap-autoloader@0.18.12`（2026-11-01 npm 最新）；雲端沙盒無法連 CDN，渲染已用本機套件驗證）
- 重新產生：
  ```bash
  python tools/sync_mindmap.py
  ```
  腳本只用 Python 標準庫，不用安裝任何東西。

## 檔案地圖

| 檔案 | 用途 |
|---|---|
| `MINDMAP.md` | 總圖（老闆編輯） |
| `mindmap.html` | 總圖可視化（腳本產生） |
| `docs/01-feasibility.md` | 可行性分析與來源 |
| `docs/02-prd.md` | 一頁式 PRD、本版不做、商業評分 |
| `docs/03-architecture.md` | 架構、迴圈、資料格式、API 用法 |
| `docs/04-roadmap.md` | 里程碑 M0～M4 與任務 |
| `docs/05-decisions.md` | 待決策 D1～D7（建議答案制） |
| `docs/adr/` | 拍板後的決策備忘卡 |
| `tools/sync_mindmap.py` | 同步腳本 |
| `CHANGELOG.md` | 每次同步紀錄 |

## 注意

本資料夾暫放在 `xiaoye-legal` repo 內（該 repo 原本是「小夜」App 的法律頁面）。D6 建議拍板後搬到獨立 repo。
