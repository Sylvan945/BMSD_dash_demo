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
