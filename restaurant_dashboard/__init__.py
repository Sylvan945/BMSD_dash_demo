"""台灣餐廳資料探索應用程式。"""

from pathlib import Path

from dash import Dash

from .callbacks import register_callbacks
from .layout import build_layout


def create_app():
    """建立應用程式，設定既有樣式目錄並註冊頁面與回呼。"""
    app = Dash(
        __name__,
        title="台灣餐廳資料探索",
        assets_folder=str(Path(__file__).resolve().parent.parent / "assets"),
    )
    app.layout = build_layout()
    register_callbacks(app)
    return app
