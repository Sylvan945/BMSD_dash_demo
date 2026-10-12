"""台灣餐廳資料探索 Demo 的啟動入口。

執行 python app.py 啟動；部署時仍可使用 app:server。
"""

from restaurant_dashboard import create_app

app = create_app()
server = app.server


if __name__ == "__main__":
    app.run(debug=True)
