"""總覽搜尋、分頁、摘要與圖表更新。"""

from dash import Input, Output, State, ctx, html

from ..config import RESULT_PAGE_SIZE
from ..data import RESTAURANTS
from ..components import result_card
from ..figures import build_ranking_figure, build_cuisine_pie, build_map_figure

def reset_filters(_clicks: int):
    """將複合搜尋條件恢復為初始狀態。"""
    return "", None, None, []


def update_page(
    previous_clicks: int,
    next_clicks: int,
    _keyword: str | None,
    _city: str | None,
    _status: str | None,
    _extras: list[str],
    current_page: int,
):
    """篩選異動時回到第一頁；只有翻頁按鈕會增減頁碼。"""
    from dash import ctx

    if ctx.triggered_id == "next-page":
        return max(1, (current_page or 1) + 1)
    if ctx.triggered_id == "previous-page":
        return max(1, (current_page or 1) - 1)
    return 1


def update_dashboard(
    keyword: str | None,
    city: str | None,
    status: str | None,
    extras: list[str] | None,
    current_page: int,
):
    """執行複合式搜尋，並將同一份結果提供給所有視覺區塊。"""
    filtered = RESTAURANTS.copy()

    # 文字搜尋同時比對餐廳名稱、完整地址與簡介。
    if keyword and keyword.strip():
        filtered = filtered[
            filtered["search_text"].str.contains(keyword.strip().lower(), regex=False, na=False)
        ]
    if city:
        filtered = filtered[filtered["city"] == city]
    if status:
        filtered = filtered[filtered["status"] == status]

    selected_extras = extras or []
    if "has_hours" in selected_extras:
        filtered = filtered[filtered["service_time"].str.strip().ne("")]
    if "has_website" in selected_extras:
        filtered = filtered[filtered["website"].str.strip().ne("")]

    # 依餐廳名稱排序，讓相同條件每次顯示的結果順序一致。
    filtered = filtered.sort_values(["city", "town", "name"], kind="stable")
    total = len(filtered)
    city_count = filtered["city"].nunique() if total else 0
    hours_count = int(filtered["service_time"].str.strip().ne("").sum()) if total else 0
    hours_ratio = round(hours_count / total * 100) if total else 0

    # 計算分頁範圍；頁碼超出時自動停在最後一頁。
    total_pages = max(1, (total + RESULT_PAGE_SIZE - 1) // RESULT_PAGE_SIZE)
    page = min(max(current_page or 1, 1), total_pages)
    start = (page - 1) * RESULT_PAGE_SIZE
    page_rows = filtered.iloc[start : start + RESULT_PAGE_SIZE]

    if total:
        cards = [result_card(row) for _, row in page_rows.iterrows()]
        result_summary = f"共 {total:,} 筆，依縣市、地區與店名排序"
    else:
        cards = [
            html.Div(
                [html.Strong("找不到符合條件的餐廳"), html.P("請嘗試放寬縣市、狀態或資料條件。")],
                className="empty-state",
            )
        ]
        result_summary = "共 0 筆，請調整搜尋條件"

    return (
        f"{total:,} 家",
        f"{city_count} 個",
        f"{hours_ratio}%",
        build_ranking_figure(filtered),
        build_cuisine_pie(filtered),
        build_map_figure(filtered),
        result_summary,
        cards,
        f"第 {page} / {total_pages} 頁",
        page <= 1,
        page >= total_pages,
    )


def register_callbacks(app):
    """將此功能的互動回呼註冊到指定 Dash 應用程式。"""
    app.callback(
        Output("keyword", "value"),
        Output("city", "value"),
        Output("status", "value"),
        Output("extras", "value"),
        Input("reset", "n_clicks"),
        prevent_initial_call=True,
    )(reset_filters)
    app.callback(
        Output("current-page", "data"),
        Input("previous-page", "n_clicks"),
        Input("next-page", "n_clicks"),
        Input("keyword", "value"),
        Input("city", "value"),
        Input("status", "value"),
        Input("extras", "value"),
        State("current-page", "data"),
    )(update_page)
    app.callback(
        Output("metric-count", "children"),
        Output("metric-cities", "children"),
        Output("metric-hours", "children"),
        Output("ranking", "figure"),
        Output("overview-cuisine-pie", "figure"),
        Output("restaurant-map", "figure"),
        Output("result-summary", "children"),
        Output("result-list", "children"),
        Output("page-indicator", "children"),
        Output("previous-page", "disabled"),
        Output("next-page", "disabled"),
        Input("keyword", "value"),
        Input("city", "value"),
        Input("status", "value"),
        Input("extras", "value"),
        Input("current-page", "data"),
    )(update_dashboard)
