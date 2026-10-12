"""集中註冊各功能的 Dash 回呼。"""

from . import explorer, navigation, overview, planner


def register_callbacks(app):
    """註冊全部分頁的互動功能。"""
    for module in (navigation, explorer, planner, overview):
        module.register_callbacks(app)
