"""分頁切換與從規劃頁前往店家詳細資料。"""

from dash import ALL, Input, Output, ctx, no_update

from ..data import RESTAURANTS

def switch_view(active_tab: str):
    """依目前選取的分頁顯示資料總覽、店家探索或餐廳規劃。"""
    if active_tab == "explorer":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}
    if active_tab == "planner":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}, {"display": "none"}


def navigate_to_restaurant_detail(click_counts: list[int]):
    """取得被點擊的店家 ID，並準備店家探索頁所需的導覽資料。"""
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or not any(click_counts or []):
        return no_update, no_update, no_update, no_update, no_update

    restaurant_id = triggered.get("restaurant_id")
    selected = RESTAURANTS[RESTAURANTS["id"] == restaurant_id]
    if selected.empty:
        return no_update, no_update, no_update, no_update, no_update

    # 加入點擊次數，確保再次點擊同一家店時 Store 仍會產生新的導覽事件。
    click_sequence = sum(click_counts or [])
    return (
        "explorer",
        selected.iloc[0]["city"],
        "",
        [],
        {"restaurant_id": restaurant_id, "click_sequence": click_sequence},
    )


def register_callbacks(app):
    """將此功能的互動回呼註冊到指定 Dash 應用程式。"""
    app.callback(
        Output("overview-tab-content", "style"),
        Output("explorer-tab-content", "style"),
        Output("planner-tab-content", "style"),
        Input("view-tabs", "value"),
    )(switch_view)
    app.callback(
        Output("view-tabs", "value"),
        Output("explorer-city", "value"),
        Output("explorer-keyword", "value"),
        Output("explorer-cuisines", "value"),
        Output("navigate-restaurant-store", "data"),
        Input({"type": "planner-detail-button", "restaurant_id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )(navigate_to_restaurant_detail)
