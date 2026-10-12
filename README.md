# BUSINESS MANAGEMENT SOFTWARE DESIGN
# 台灣餐廳資料探索 Demo

此 Demo 直接讀取 `datasets/RestaurantList.json`，提供：

- 縣市餐廳數量排行榜與菜色類型比例圓餅圖
- 台灣餐廳分布地圖
- 店名／地址／簡介關鍵字、縣市、營業狀態與資料完整度的複合搜尋
- 可切換的「店家探索」分頁，可依縣市、店名／簡介關鍵字與多選菜色類型搜尋；初始不載入資料，搜尋後才顯示店家基本資料、社群帳號與聚焦地圖，沒有符合店家時會顯示提醒
- 可切換的「餐廳規劃」分頁；進入分頁並選定縣市後，可用雙頭時間 RangeSlider 與多選菜色類型尋找餐廳，完整展開符合店家，並可從卡片按鈕跳至店家探索詳細資料
## 啟動方式

```powershell
# 安裝執行所需套件
pip install -r requirements.txt

# 啟動 Dash 開發伺服器
python app.py
```

啟動後，請開啟終端機顯示的本機網址（預設為 `http://127.0.0.1:8050`）。

## 程式架構與各檔案用途

啟動方式維持 `python app.py`，部署入口維持 `app:server`。程式依功能拆成以下檔案：

| 檔案 | 功用 |
| --- | --- |
| `app.py` | 啟動入口，建立 Dash 應用程式並提供 `app`、`server`。 |
| `restaurant_dashboard/__init__.py` | `create_app()` 工廠，組合頁面、註冊回呼，指定專案根目錄的 `assets/` 樣式。 |
| `restaurant_dashboard/config.py` | 集中管理資料檔路徑、每頁結果數與菜色分類中文名稱。 |
| `restaurant_dashboard/data.py` | 載入兩份 JSON、補齊營業時間、整理社群網址與搜尋欄位，建立共用 DataFrame 及下拉選單選項。 |
| `restaurant_dashboard/time_utils.py` | 解析營業時間文字、比對用餐時段（含跨午夜營業）、格式化時間標籤。 |
| `restaurant_dashboard/figures.py` | 產生縣市排行榜、餐廳分布地圖、單店地圖及菜色分類圓餅圖。 |
| `restaurant_dashboard/components.py` | 可重用的摘要卡片、餐廳結果卡片及店家詳細資料欄位。 |
| `restaurant_dashboard/layout.py` | `build_layout()` 建立三個分頁的畫面、搜尋控制項、圖表容器與狀態儲存元件。 |
| `restaurant_dashboard/callbacks/__init__.py` | 統一註冊所有功能的 Dash 回呼。 |
| `restaurant_dashboard/callbacks/overview.py` | 資料總覽的複合搜尋、重設條件、翻頁、摘要數字及圖表更新。 |
| `restaurant_dashboard/callbacks/explorer.py` | 店家探索的篩選選項、店家詳細資料、社群連結及單店地圖更新。 |
| `restaurant_dashboard/callbacks/planner.py` | 依縣市、用餐時間及菜色條件規劃餐廳，產生摘要、地圖與全部結果卡片。 |
| `restaurant_dashboard/callbacks/navigation.py` | 切換分頁顯示狀態，以及從規劃結果跳至指定店家的詳細資料。 |
