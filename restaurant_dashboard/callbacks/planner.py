"""用餐時間、縣市與菜色條件的餐廳規劃。"""

from dash import Input, Output, html, no_update

from ..data import RESTAURANTS
from ..components import result_card
from ..figures import build_map_figure
from ..time_utils import format_time_range, is_open_during

def update_planner(
    active_tab: str,
    selected_time: list[float] | None,
    city: str | None,
    cuisine_codes: list[int] | None,
):
    """套用規劃條件，回傳時間標籤、摘要、地圖與全部符合店家。"""
    # 第三頁尚未開啟時不建立大量卡片，避免初次載入長時間停在 Updating。
    if active_tab != "planner":
        return no_update, no_update, no_update, no_update

    time_range = selected_time or [11.5, 13.5]
    start_time, end_time = map(float, time_range)

    # 規劃頁要求先選定縣市，防止一次產生全臺數千張卡片拖慢瀏覽器。
    if not city:
        empty_map = build_map_figure(RESTAURANTS.iloc[0:0])
        return (
            format_time_range([start_time, end_time]),
            "請先選擇縣市，再開始規劃餐廳。",
            empty_map,
            [html.Div("請先選擇縣市。", className="empty-state")],
        )

    filtered = RESTAURANTS[RESTAURANTS["status"] == "營業中"].copy()

    # 已知時段的店家必須符合選定時間；缺少時段資料的店家仍保留，
    # 但會在摘要中列為「待確認」，避免資料缺漏讓整個縣市沒有結果。
    filtered["time_confirmed"] = filtered["time_ranges"].map(
        lambda ranges: is_open_during(ranges, start_time, end_time)
    ).astype(bool)
    filtered["time_unknown"] = filtered["time_ranges"].map(lambda ranges: not bool(ranges))
    filtered = filtered.loc[filtered["time_confirmed"] | filtered["time_unknown"]]
    if city:
        filtered = filtered[filtered["city"] == city]

    selected_codes = set(cuisine_codes or [])
    if selected_codes:
        cuisine_mask = filtered["cuisine_codes"].map(
            lambda codes: bool(selected_codes.intersection(codes))
        ).astype(bool)
        filtered = filtered.loc[cuisine_mask]

    filtered = filtered.sort_values(
        ["time_confirmed", "city", "town", "name"],
        ascending=[False, True, True, True],
        kind="stable",
    )
    result_count = len(filtered)
    confirmed_count = int(filtered["time_confirmed"].sum()) if result_count else 0
    unknown_count = int(filtered["time_unknown"].sum()) if result_count else 0
    time_text = format_time_range([start_time, end_time])
    summary = (
        f"{time_text} 預計用餐，共 {result_count:,} 家；"
        f"時間確認符合 {confirmed_count:,} 家，營業時間待確認 {unknown_count:,} 家"
    )

    planner_map = build_map_figure(filtered)
    planner_map.update_layout(height=510)

    if result_count:
        # 使用者希望查看全部結果，因此不再截取前 12 筆或顯示剩餘筆數提示。
        result_items = [
            result_card(row, show_detail_button=True)
            for _, row in filtered.iterrows()
        ]
    else:
        result_items = [
            html.Div(
                [
                    html.Strong("目前條件找不到餐廳"),
                    html.P("請調整用餐時間、清除部分菜色類型，或改選其他縣市。"),
                ],
                className="empty-state",
            )
        ]

    return time_text, summary, planner_map, result_items


def register_callbacks(app):
    """將此功能的互動回呼註冊到指定 Dash 應用程式。"""
    app.callback(
        Output("planner-time-label", "children"),
        Output("planner-summary", "children"),
        Output("planner-map", "figure"),
        Output("planner-results", "children"),
        Input("view-tabs", "value"),
        Input("planner-time", "value"),
        Input("planner-city", "value"),
        Input("planner-cuisines", "value"),
    )(update_planner)
