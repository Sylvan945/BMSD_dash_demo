"""台灣餐廳資料探索 Demo。

此程式以專案內的 RestaurantList.json 為資料來源，提供：
1. 縣市餐廳數量排行榜
2. 台灣餐廳分布地圖
3. 餐廳複合式搜尋功能
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, State, callback, dcc, html


# -----------------------------------------------------------------------------
# 基本設定：集中管理資料路徑與列表顯示上限，方便 Demo 後續調整。
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "datasets" / "RestaurantList.json"
SERVICE_TIME_FILE = BASE_DIR / "datasets" / "RestaurantServiceTimeList.json"
RESULT_PAGE_SIZE = 12


# -----------------------------------------------------------------------------
# 資料整理：把原始 JSON 中的巢狀欄位攤平成表格，供圖表與搜尋共用。
# -----------------------------------------------------------------------------
def first_value(items: Any, key: str) -> str:
    """安全地取得物件陣列中第一筆指定欄位，缺值時回傳空字串。"""
    if not isinstance(items, list) or not items:
        return ""
    first_item = items[0]
    return str(first_item.get(key, "")) if isinstance(first_item, dict) else str(first_item)


def load_restaurants() -> tuple[pd.DataFrame, str]:
    """讀取餐廳資料並轉為適合 Dash 使用的 DataFrame。"""
    # 原始檔含 UTF-8 BOM，因此使用 utf-8-sig 避免 JSON 解析錯誤。
    with DATA_FILE.open("r", encoding="utf-8-sig") as file:
        payload = json.load(file)

    # 補讀結構化營業時間資料；主檔缺少文字時，會優先用這份資料補齊。
    with SERVICE_TIME_FILE.open("r", encoding="utf-8-sig") as file:
        service_payload = json.load(file)

    service_time_lookup: dict[str, str] = {}
    for service_record in service_payload.get("RestaurantServiceTimes", []):
        time_ranges = []
        for period in service_record.get("ServiceTimes", []):
            name = str(period.get("Name") or "營業時段")
            start_time = str(period.get("StartTime") or "")[:5]
            end_time = str(period.get("EndTime") or "")[:5]
            time_ranges.append(f"{name} {start_time}-{end_time}".strip(" -"))
        service_time_lookup[str(service_record.get("RestaurantID") or "")] = "；".join(time_ranges)

    records: list[dict[str, Any]] = []
    for restaurant in payload.get("Restaurants", []):
        restaurant_id = str(restaurant.get("RestaurantID") or "")
        address = restaurant.get("PostalAddress") or {}
        city = str(address.get("City") or "未標示")
        town = str(address.get("Town") or "未標示")
        street = str(address.get("StreetAddress") or "")
        full_address = f"{city}{town}{street}"

        # 將 Demo 會使用的欄位整理成單層結構，保留原始 ID 以便追溯。
        records.append(
            {
                "id": restaurant_id,
                "name": restaurant.get("RestaurantName") or "未命名餐廳",
                "description": restaurant.get("Description") or "",
                "city": city,
                "town": town,
                "address": full_address,
                "lat": restaurant.get("PositionLat"),
                "lon": restaurant.get("PositionLon"),
                "telephone": first_value(restaurant.get("Telephones"), "Tel"),
                "service_time": restaurant.get("ServiceTimeInfo") or service_time_lookup.get(restaurant_id, ""),
                "status": "營業中" if restaurant.get("ServiceStatus") == 1 else "非營業中",
                "website": restaurant.get("WebsiteURL") or "",
                "map_url": first_value(restaurant.get("MapURLs"), "URL"),
            }
        )

    frame = pd.DataFrame(records)
    frame["lat"] = pd.to_numeric(frame["lat"], errors="coerce")
    frame["lon"] = pd.to_numeric(frame["lon"], errors="coerce")

    # 預先建立小寫搜尋字串，讓名稱、地址與簡介可用同一關鍵字搜尋。
    frame["search_text"] = (
        frame[["name", "address", "description"]]
        .fillna("")
        .agg(" ".join, axis=1)
        .str.lower()
    )
    update_time = str(payload.get("UpdateTime", "未知"))
    return frame, update_time


RESTAURANTS, DATA_UPDATE_TIME = load_restaurants()
CITY_OPTIONS = sorted(RESTAURANTS["city"].dropna().unique().tolist())


# -----------------------------------------------------------------------------
# 圖表產生器：統一排行榜與地圖的配色、留白與空資料狀態。
# -----------------------------------------------------------------------------
def build_ranking_figure(filtered: pd.DataFrame):
    """建立各縣市餐廳數量的水平長條圖。"""
    counts = (
        filtered.groupby("city", as_index=False)
        .size()
        .rename(columns={"size": "餐廳數"})
        .sort_values("餐廳數", ascending=True)
    )

    if counts.empty:
        figure = px.bar(title="目前條件沒有可排行的資料")
    else:
        figure = px.bar(
            counts,
            x="餐廳數",
            y="city",
            orientation="h",
            text="餐廳數",
            labels={"city": "縣市"},
            color="餐廳數",
            color_continuous_scale=["#dbeafe", "#2563eb", "#172554"],
        )
        figure.update_traces(textposition="outside", cliponaxis=False)

    figure.update_layout(
        template="plotly_white",
        margin=dict(l=16, r=36, t=16, b=16),
        height=max(420, 31 * max(len(counts), 1)),
        coloraxis_showscale=False,
        font=dict(family="Arial, 'Noto Sans TC', sans-serif", color="#1e293b"),
        xaxis=dict(showgrid=True, gridcolor="#e2e8f0", title=None),
        yaxis=dict(title=None, showgrid=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def build_map_figure(filtered: pd.DataFrame):
    """建立使用 OpenStreetMap 底圖的台灣餐廳散點地圖。"""
    points = filtered.dropna(subset=["lat", "lon"]).copy()

    if points.empty:
        figure = px.scatter_map()
    else:
        figure = px.scatter_map(
            points,
            lat="lat",
            lon="lon",
            hover_name="name",
            hover_data={
                "city": True,
                "town": True,
                "address": True,
                "service_time": True,
                "lat": False,
                "lon": False,
            },
            color="status",
            color_discrete_map={"營業中": "#0f766e", "非營業中": "#dc2626"},
            zoom=6.2,
            center={"lat": 23.75, "lon": 120.95},
            map_style="open-street-map",
        )
        figure.update_traces(marker={"size": 8, "opacity": 0.72})

    figure.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=570,
        legend=dict(
            title=None,
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return figure


# -----------------------------------------------------------------------------
# 畫面元件：用小函式避免版面重複，並讓結果卡片容易維護。
# -----------------------------------------------------------------------------
def metric_card(label: str, element_id: str) -> html.Div:
    """建立首頁上方的摘要數字卡。"""
    return html.Div(
        [html.Span(label, className="metric-label"), html.Strong(id=element_id)],
        className="metric-card",
    )


def result_card(row: pd.Series) -> html.Article:
    """將一筆餐廳資料轉為搜尋結果卡片。"""
    detail_items = [
        html.Span(f"📍 {row['address'] or '地址未提供'}"),
        html.Span(f"☎ {row['telephone'] or '電話未提供'}"),
        html.Span(f"🕒 {row['service_time'] or '營業時間未提供'}"),
    ]
    links = []
    if row["website"]:
        links.append(
            html.A("官方網站", href=row["website"], target="_blank", rel="noreferrer")
        )

    return html.Article(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(row["name"]),
                            html.Span(row["status"], className=f"status {'open' if row['status'] == '營業中' else 'closed'}"),
                        ],
                        className="result-title",
                    ),
                    html.Div(detail_items, className="result-meta"),
                ]
            ),
            html.Div(links, className="result-links") if links else None,
        ],
        className="result-card",
    )


# -----------------------------------------------------------------------------
# Dash 應用程式與頁面配置：依序呈現搜尋、摘要、圖表與結果清單。
# -----------------------------------------------------------------------------
app = Dash(__name__, title="台灣餐廳資料探索")
server = app.server

app.layout = html.Div(
    [
        html.Header(
            [
                html.Div(
                    [
                        html.P("RESTAURANT DATA DEMO", className="eyebrow"),
                        html.H1("台灣餐廳資料探索"),
                        html.P("用排行榜、地圖與複合條件快速瀏覽專案資料集。", className="subtitle"),
                    ]
                ),
                html.Div(
                    [html.Span("資料更新時間"), html.Strong(DATA_UPDATE_TIME)],
                    className="data-time",
                ),
            ],
            className="page-header",
        ),
        html.Main(
            [
                html.Section(
                    [
                        html.Div(
                            [
                                html.Label("關鍵字", htmlFor="keyword"),
                                dcc.Input(
                                    id="keyword",
                                    type="search",
                                    placeholder="搜尋店名、地址或簡介",
                                    debounce=True,
                                ),
                            ],
                            className="field field-wide",
                        ),
                        html.Div(
                            [
                                html.Label("縣市", htmlFor="city"),
                                dcc.Dropdown(
                                    id="city",
                                    options=[{"label": city, "value": city} for city in CITY_OPTIONS],
                                    placeholder="全部縣市",
                                    clearable=True,
                                ),
                            ],
                            className="field",
                        ),
                        html.Div(
                            [
                                html.Label("營業狀態", htmlFor="status"),
                                dcc.Dropdown(
                                    id="status",
                                    options=[
                                        {"label": "營業中", "value": "營業中"},
                                        {"label": "非營業中", "value": "非營業中"},
                                    ],
                                    placeholder="全部狀態",
                                    clearable=True,
                                ),
                            ],
                            className="field",
                        ),
                        html.Div(
                            [
                                html.Label("資料條件"),
                                dcc.Checklist(
                                    id="extras",
                                    options=[
                                        {"label": "有營業時間", "value": "has_hours"},
                                        {"label": "有官方網站", "value": "has_website"},
                                    ],
                                    value=[],
                                    className="check-list",
                                ),
                            ],
                            className="field extras-field",
                        ),
                        html.Button("清除條件", id="reset", n_clicks=0, className="reset-button"),
                    ],
                    className="filter-panel",
                    **{"aria-label": "餐廳搜尋條件"},
                ),
                html.Section(
                    [
                        metric_card("符合條件", "metric-count"),
                        metric_card("涵蓋縣市", "metric-cities"),
                        metric_card("有營業時間", "metric-hours"),
                    ],
                    className="metric-grid",
                    **{"aria-label": "搜尋摘要"},
                ),
                html.Section(
                    [
                        html.Article(
                            [
                                html.Div(
                                    [html.H2("縣市餐廳數量排行榜"), html.P("依目前搜尋條件即時重新計算")],
                                    className="section-heading",
                                ),
                                dcc.Loading(dcc.Graph(id="ranking", config={"displayModeBar": False})),
                            ],
                            className="panel ranking-panel",
                        ),
                        html.Article(
                            [
                                html.Div(
                                    [html.H2("台灣餐廳分布地圖"), html.P("滑過標記可查看店家資訊")],
                                    className="section-heading",
                                ),
                                dcc.Loading(dcc.Graph(id="restaurant-map", config={"displayModeBar": False})),
                            ],
                            className="panel map-panel",
                        ),
                    ],
                    className="visual-grid",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.Div([html.H2("搜尋結果"), html.P(id="result-summary")]),
                                html.Div(
                                    [
                                        html.Button("上一頁", id="previous-page", n_clicks=0),
                                        html.Span(id="page-indicator"),
                                        html.Button("下一頁", id="next-page", n_clicks=0),
                                    ],
                                    className="pagination",
                                ),
                            ],
                            className="section-heading result-heading",
                        ),
                        dcc.Store(id="current-page", data=1),
                        html.Div(id="result-list", className="result-list"),
                    ],
                    className="panel results-panel",
                ),
            ]
        ),
        html.Footer("資料來源：專案 datasets/RestaurantList.json｜本頁僅供功能展示"),
    ],
    className="app-shell",
)


# -----------------------------------------------------------------------------
# 互動回呼：清除按鈕一次重設所有搜尋控制項。
# -----------------------------------------------------------------------------
@callback(
    Output("keyword", "value"),
    Output("city", "value"),
    Output("status", "value"),
    Output("extras", "value"),
    Input("reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_clicks: int):
    """將複合搜尋條件恢復為初始狀態。"""
    return "", None, None, []


# -----------------------------------------------------------------------------
# 互動回呼：篩選條件或翻頁按鈕改變時，決定目前頁碼。
# -----------------------------------------------------------------------------
@callback(
    Output("current-page", "data"),
    Input("previous-page", "n_clicks"),
    Input("next-page", "n_clicks"),
    Input("keyword", "value"),
    Input("city", "value"),
    Input("status", "value"),
    Input("extras", "value"),
    State("current-page", "data"),
)
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


# -----------------------------------------------------------------------------
# 互動回呼：套用複合條件，同步更新摘要、排行榜、地圖與結果清單。
# -----------------------------------------------------------------------------
@callback(
    Output("metric-count", "children"),
    Output("metric-cities", "children"),
    Output("metric-hours", "children"),
    Output("ranking", "figure"),
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
)
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
        build_map_figure(filtered),
        result_summary,
        cards,
        f"第 {page} / {total_pages} 頁",
        page <= 1,
        page >= total_pages,
    )


# -----------------------------------------------------------------------------
# 本機啟動入口：執行 `python app.py` 後即可開啟瀏覽器查看 Demo。
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
