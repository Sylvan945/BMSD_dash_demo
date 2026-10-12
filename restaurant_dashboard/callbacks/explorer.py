"""店家探索篩選與詳細資料更新。"""

from dash import Input, Output, State, html

import plotly.express as px

from ..data import RESTAURANTS
from ..components import detail_field
from ..figures import build_detail_map

def update_explorer_restaurants(
    city: str | None,
    keyword: str | None,
    cuisine_codes: list[int] | None,
    navigation_data: dict | None,
    current_id: str | None,
):
    """依縣市、簡介關鍵字與菜色類型產生店家清單。"""
    selected_codes = set(cuisine_codes or [])
    has_search_condition = bool(city or (keyword and keyword.strip()) or selected_codes)

    # 初始狀態不提供店家清單，使用者設定任一搜尋條件後才載入資料。
    if not has_search_condition:
        return [], None, True, {"display": "block"}, {"display": "none"}

    filtered = RESTAURANTS.copy()
    if city:
        filtered = filtered[filtered["city"] == city]
    if keyword and keyword.strip():
        normalized_keyword = keyword.strip().lower()
        filtered = filtered[
            filtered["search_text"].str.contains(
                normalized_keyword,
                regex=False,
                na=False,
            )
        ]
    if selected_codes:
        cuisine_mask = filtered["cuisine_codes"].map(
            lambda codes: bool(selected_codes.intersection(codes))
        ).astype(bool)
        filtered = filtered.loc[cuisine_mask]

    options = [
        {
            "label": f"{row['name']}｜{row['town']}",
            "value": row["id"],
        }
        for _, row in filtered.sort_values(["town", "name"], kind="stable").iterrows()
    ]

    # 從規劃頁跳轉時優先選取指定店家；一般切換縣市則盡量保留目前店家。
    valid_ids = {option["value"] for option in options}
    requested_id = (navigation_data or {}).get("restaurant_id")
    if requested_id in valid_ids:
        selected_id = requested_id
    elif current_id in valid_ids:
        selected_id = current_id
    else:
        selected_id = options[0]["value"] if options else None
    # 一旦使用者開始搜尋就隱藏初始提示；沒有結果時顯示查無店家訊息。
    no_results_style = {"display": "block"} if not options else {"display": "none"}
    return options, selected_id, not bool(options), {"display": "none"}, no_results_style


def update_restaurant_detail(restaurant_id: str | None):
    """依餐廳 ID 產生詳細資料區塊與聚焦地圖。"""
    selected = RESTAURANTS[RESTAURANTS["id"] == restaurant_id]
    if selected.empty:
        # 初始狀態的詳細區塊會隱藏，因此只需提供安全的空圖表物件。
        empty_figure = px.scatter_map()
        empty_figure.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=500,
        )
        return (
            html.Div("請先選擇店家。", className="empty-state"),
            empty_figure,
            {"display": "none"},
        )

    row = selected.iloc[0]

    # 社群欄位若沒有資料，仍保留明確的空狀態提示。
    social_links = [
        html.A(
            item["platform"],
            href=item["url"],
            target="_blank",
            rel="noreferrer",
            className="detail-link social-link",
        )
        for item in row["social_urls"]
    ]
    if not social_links:
        social_links = [html.Span("資料集未提供社群帳號", className="missing-data")]

    external_links = []
    if row["website"]:
        external_links.append(
            html.A(
                "店家網站",
                href=row["website"],
                target="_blank",
                rel="noreferrer",
                className="detail-link",
            )
        )
    if row["map_url"]:
        external_links.append(
            html.A(
                "開啟外部地圖",
                href=row["map_url"],
                target="_blank",
                rel="noreferrer",
                className="detail-link secondary-link",
            )
        )

    detail = html.Div(
        [
            html.Div(
                [
                    html.P(f"{row['city']} · {row['town']}", className="detail-location"),
                    html.Div(
                        [
                            html.H2(row["name"]),
                            html.Span(
                                row["status"],
                                className=f"status {'open' if row['status'] == '營業中' else 'closed'}",
                            ),
                        ],
                        className="detail-title",
                    ),
                ],
                className="detail-header",
            ),
            html.Div(
                [
                    detail_field("完整地址", row["address"]),
                    detail_field("聯絡電話", row["telephone"]),
                    detail_field("營業時間", row["service_time"]),
                    detail_field("資料編號", row["id"]),
                ],
                className="detail-fields",
            ),
            html.Div(
                [html.H3("店家介紹"), html.P(row["description"] or "資料集未提供店家介紹。")],
                className="detail-description",
            ),
            html.Div(
                [html.H3("社群帳號"), html.Div(social_links, className="detail-links")],
                className="detail-social",
            ),
            html.Div(external_links, className="detail-actions") if external_links else None,
        ],
        className="detail-content",
    )
    return detail, build_detail_map(row), {"display": "grid"}


def register_callbacks(app):
    """將此功能的互動回呼註冊到指定 Dash 應用程式。"""
    app.callback(
        Output("restaurant-picker", "options"),
        Output("restaurant-picker", "value"),
        Output("restaurant-picker", "disabled"),
        Output("explorer-search-hint", "style"),
        Output("explorer-no-results", "style"),
        Input("explorer-city", "value"),
        Input("explorer-keyword", "value"),
        Input("explorer-cuisines", "value"),
        Input("navigate-restaurant-store", "data"),
        State("restaurant-picker", "value"),
    )(update_explorer_restaurants)
    app.callback(
        Output("restaurant-detail", "children"),
        Output("detail-map", "figure"),
        Output("explorer-details", "style"),
        Input("restaurant-picker", "value"),
    )(update_restaurant_detail)
