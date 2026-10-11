# 投資人行事曆

台股法說會（Yahoo 股市）、股東會（玩股網）每天早上 7 點自動更新；
央行會議、美股財報、年度大會等放在 `data/events_manual.json`，由人工整理。

## 第一次架設（全程在網頁上操作）

1. 登入 GitHub → 右上角 **+** → **New repository**，名稱例如 `investor-calendar`，選 **Public**，按 **Create repository**。
2. 在新頁面按 **uploading an existing file**，把這個資料夾裡的 `index.html`、`README.md`、`data` 資料夾、`scripts` 資料夾**整個拖進去**，按 **Commit changes**。
3. 工作流程檔要放在隱藏資料夾：在儲存庫首頁按 **Add file → Create new file**，檔名欄位輸入 `.github/workflows/update.yml`（輸入斜線會自動變成資料夾），把 `update.yml` 的內容整份貼上，按 **Commit changes**。
4. **Settings → Actions → General → Workflow permissions**，選 **Read and write permissions**，按 Save。
5. **Settings → Pages → Build and deployment**：Source 選 **Deploy from a branch**，Branch 選 `main`、資料夾 `/ (root)`，按 Save。
6. 到 **Actions** 頁籤 → 左邊點「更新行事曆資料」→ **Run workflow**，手動跑第一次。綠色勾勾代表成功。
7. 約一兩分鐘後，網址是 `https://你的帳號.github.io/investor-calendar/`。

之後不用再做任何事，每天會自動更新。

## 已經架設過、只要換新版

把新版的 `index.html`、`data/events_manual.json`、`data/events.json`、`scripts/update.py` 與 `update.yml` 上傳覆蓋舊檔
（舊的 `scripts/list_endpoints.py` 可以刪掉），再到 Actions 手動跑一次。

## 日常維護

- **新增或修改美股財報、央行、大會日期**：編輯 `data/events_manual.json`（鉛筆圖示），存檔後到 Actions 手動跑一次即可。
  欄位：`d` 日期、`e` 結束日、`c` 類別（macro / us / tech）、`t` 標題、`tm` 時間、`pl` 地點、`n` 備註、`st`（`o` 官方、`e` 預估）、`u` 來源連結、`k` 倒數磚代號。
- **哪些公司的法說會算「主要事件」**：編輯 `scripts/update.py` 最上方的 `BIG`（代號清單）。
- **看更新有沒有成功**：Actions 頁籤，紅色叉叉就點進去看訊息。
  某個來源失敗時，網站會沿用上一次的資料，不會變空。

## 資料來源

- 法說會：https://tw.stock.yahoo.com/calendar/earnings-call
- 股東會：https://www.wantgoo.com/stock/calendar/shareholders-meeting
- 其餘為各公司與機構官方公告，連結在每筆事件裡。

## 已知限制

- 兩個來源的頁面如果改版，解析可能失效。這時 Actions 會顯示警告，網站沿用舊資料，需要請 Claude 重新調整 `scripts/update.py`。
- 自動抓取尚未在 GitHub 的真實環境跑過；第一次手動執行後請看一下 Actions 的紀錄。
