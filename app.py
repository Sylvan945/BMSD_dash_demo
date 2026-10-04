"""台灣餐廳資料探索 Demo。

此程式以專案內的 RestaurantList.json 為資料來源，提供：
1. 縣市餐廳數量排行榜
2. 台灣餐廳分布地圖
3. 餐廳複合式搜尋功能
"""

#from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html, no_update


# -----------------------------------------------------------------------------
# 基本設定：集中管理資料路徑與列表顯示上限，方便 Demo 後續調整。
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "datasets" / "RestaurantList.json"
SERVICE_TIME_FILE = BASE_DIR / "datasets" / "RestaurantServiceTimeList.json"
RESULT_PAGE_SIZE = 12

# 依交通部觀光資料標準 V2.1 將 CuisineClassEnum 代碼轉為中文名稱。
CUISINE_LABELS = {
    1: "台灣小吃／台菜",
    2: "中式料理",
    3: "港式料理",
    4: "日式料理",
    5: "韓式料理",
    96: "南亞料理",
    97: "東南亞料理",
    98: "美式／歐式料理",
    99: "其他異國料理",
    100: "夜市小吃",
    101: "甜點冰品",
    102: "麵包糕點",
    103: "咖啡／茶等非酒精飲品",
    104: "酒類飲品",
    105: "燒烤／鐵板燒",
    106: "火鍋",
    107: "海鮮",
    108: "牛排",
    109: "速食",
    110: "連鎖餐飲",
    111: "吃到飽",
    112: "便當／自助餐",
    113: "牛肉麵",
    114: "粥品",
    115: "地方特產",
    116: "伴手禮",
    200: "純素飲食",
    201: "素食飲食",
    202: "清真飲食",
    203: "無麩質飲食",
    204: "健康飲食",
    254: "其他",
}


# -----------------------------------------------------------------------------
# 資料整理：把原始 JSON 中的巢狀欄位攤平成表格，供圖表與搜尋共用。
# -----------------------------------------------------------------------------
def first_value(items: Any, key: str) -> str:
    """安全地取得物件陣列中第一筆指定欄位，缺值時回傳空字串。"""
    if not isinstance(items, list) or not items:
        return ""
    first_item = items[0]
    return str(first_item.get(key, "")) if isinstance(first_item, dict) else str(first_item)


def collect_urls(value: Any) -> list[str]:
    """將字串、字串陣列或含 URL 欄位的物件陣列統一整理成網址陣列。"""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []

    urls: list[str] = []
    for item in value:
        url = item.get("URL", "") if isinstance(item, dict) else item
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls


def social_platform(url: str) -> str | None:
    """依網址網域判斷常見社群平台；不是社群網址時回傳 None。"""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    platforms = {
        "facebook.com": "Facebook",
        "instagram.com": "Instagram",
        "line.me": "LINE",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "threads.net": "Threads",
        "twitter.com": "X / Twitter",
        "x.com": "X / Twitter",
    }
    for domain, label in platforms.items():
        if host == domain or host.endswith(f".{domain}"):
            return label
    return None


def parse_time_ranges(service_time: str) -> list[tuple[float, float]]:
    """從營業時間文字擷取可供 Slider 比對的開始與結束時間。"""
    if not service_time:
        return []
    if "24小時" in service_time:
        return [(0.0, 24.0)]

    # 統一全形冒號與各式連接符號，處理不同機關提供的文字格式。
    normalized = (
        service_time.replace("：", ":")
        .replace("–", "-")
        .replace("—", "-")
        .replace("~", "-")
        .replace("～", "-")
    )
    matches = re.findall(r"(?<!\d)(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", normalized)
    ranges: list[tuple[float, float]] = []
    for start_hour, start_minute, end_hour, end_minute in matches:
        start = int(start_hour) + int(start_minute) / 60
        end = int(end_hour) + int(end_minute) / 60
        if start <= 24 and end <= 24 and start != end:
            ranges.append((start, end))
    return ranges


def is_open_during(
    ranges: list[tuple[float, float]],
    start_time: float,
    end_time: float,
) -> bool:
    """判斷任一營業時段是否完整涵蓋 Slider 選定的用餐時間範圍。"""
    for start, end in ranges:
        if start < end and start <= start_time and end_time <= end:
            return True
        # 跨午夜營業時段會拆成深夜與凌晨兩段判斷；RangeSlider 本身不跨日。
        if start > end and (
            (start_time >= start and end_time <= 24)
            or (start_time >= 0 and end_time <= end)
        ):
            return True
    return False


def format_time(value: float) -> str:
    """將 Slider 的小時數值轉成 HH:MM 顯示文字。"""
    hour = int(value)
    minute = int(round((value - hour) * 60))
    return f"{hour:02d}:{minute:02d}"


def format_time_range(values: list[float]) -> str:
    """將 RangeSlider 的兩個數值轉成可閱讀的用餐時間範圍。"""
    start, end = values
    return f"{format_time(start)}–{format_time(end)}"


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
        website = str(restaurant.get("WebsiteURL") or "").strip()
        service_time = restaurant.get("ServiceTimeInfo") or service_time_lookup.get(restaurant_id, "")

        # 原始 SocialMediaURLs 可能為空，因此也從 WebsiteURL 與 SameAsURLs
        # 辨識常見社群平台，讓店家探索頁能呈現資料集中實際存在的帳號。
        candidate_urls = (
            collect_urls(restaurant.get("SocialMediaURLs"))
            + collect_urls(restaurant.get("SameAsURLs"))
            + collect_urls(website)
        )
        social_urls = [
            {"platform": social_platform(url), "url": url}
            for url in dict.fromkeys(candidate_urls)
            if social_platform(url)
        ]

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
                "service_time": service_time,
                "time_ranges": parse_time_ranges(service_time),
                "cuisine_codes": restaurant.get("CuisineClasses") or [],
                "status": "營業中" if restaurant.get("ServiceStatus") == 1 else "非營業中",
                "website": "" if social_platform(website) else website,
                "social_urls": social_urls,
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
PLANNER_DEFAULT_CITY = CITY_OPTIONS[0] if CITY_OPTIONS else None
AVAILABLE_CUISINE_CODES = sorted(
    {code for codes in RESTAURANTS["cuisine_codes"] for code in codes}
)
CUISINE_OPTIONS = [
    {
        "label": CUISINE_LABELS.get(code, f"其他類型（代碼 {code}）"),
        "value": code,
    }
    for code in AVAILABLE_CUISINE_CODES
]


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


def build_detail_map(row: pd.Series):
    """建立聚焦單一店家的詳細位置地圖。"""
    point = pd.DataFrame([row])
    figure = px.scatter_map(
        point,
        lat="lat",
        lon="lon",
        hover_name="name",
        hover_data={"address": True, "lat": False, "lon": False},
        zoom=15,
        center={"lat": row["lat"], "lon": row["lon"]},
        map_style="open-street-map",
    )
    figure.update_traces(marker={"size": 17, "color": "#dc2626", "opacity": 0.9})
    figure.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=500,
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def build_cuisine_pie(filtered: pd.DataFrame):
    """建立目前規劃結果中各菜色分類標記的圓餅圖。"""
    counts = Counter(
        code
        for codes in filtered["cuisine_codes"]
        for code in codes
    )

    if not counts:
        figure = px.pie(names=[], values=[])
        figure.add_annotation(
            text="目前條件沒有可統計的菜色分類",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "#64748b"},
        )
    else:
        cuisine_counts = pd.DataFrame(
            [
                {
                    "菜色類型": CUISINE_LABELS.get(code, f"其他類型（代碼 {code}）"),
                    "店家數": count,
                }
                for code, count in counts.most_common()
            ]
        )
        figure = px.pie(
            cuisine_counts,
            names="菜色類型",
            values="店家數",
            hole=0.38,
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        figure.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate="%{label}<br>%{value} 家標記<br>%{percent}<extra></extra>",
        )

    figure.update_layout(
        height=430,
        margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(
            title="菜色類型",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.01,
            font={"size": 12},
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


def result_card(row: pd.Series, show_detail_button: bool = False) -> html.Article:
    """將一筆餐廳資料轉為結果卡片，規劃頁可額外加入詳細資料按鈕。"""
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
    if show_detail_button:
        links.append(
            html.Button(
                "查看店家詳細資料",
                id={"type": "planner-detail-button", "restaurant_id": row["id"]},
                n_clicks=0,
                className="detail-navigation-button",
            )
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


def detail_field(label: str, value: str) -> html.Div:
    """建立店家探索頁中的單一基本資料欄位。"""
    return html.Div(
        [html.Span(label, className="detail-label"), html.Strong(value or "資料未提供")],
        className="detail-field",
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
                # 以分頁切換資料總覽與單店探索，兩區內容會保留在頁面中，
                # 因此切換時不需要重新載入資料或重建圖表元件。
                dcc.Tabs(
                    id="view-tabs",
                    value="overview",
                    children=[
                        dcc.Tab(label="資料總覽", value="overview"),
                        dcc.Tab(label="店家探索", value="explorer"),
                        dcc.Tab(label="餐廳規劃", value="planner"),
                    ],
                    className="view-tabs",
                ),
                # 暫存第三頁選取的店家，供第二頁載入對應縣市與詳細資料。
                dcc.Store(id="navigate-restaurant-store"),
                html.Div(
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
                                    [
                                        html.H2("菜色類型比例"),
                                        html.P("依目前搜尋結果的分類標記統計"),
                                    ],
                                    className="section-heading",
                                ),
                                dcc.Loading(
                                    dcc.Graph(
                                        id="overview-cuisine-pie",
                                        config={"displayModeBar": False},
                                    )
                                ),
                            ],
                            className="panel overview-pie-panel",
                        ),
                        html.Article(
                            [
                                html.Div(
                                    [html.H2("台灣餐廳分布地圖"), html.P("滑過標記可查看店家資訊")],
                                    className="section-heading",
                                ),
                                dcc.Loading(dcc.Graph(id="restaurant-map", config={"displayModeBar": False})),
                            ],
                            className="panel map-panel overview-map-panel",
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
                    ],
                    id="overview-tab-content",
                ),
                html.Div(
                    [
                        html.Section(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Label("縣市", htmlFor="explorer-city"),
                                                dcc.Dropdown(
                                                    id="explorer-city",
                                                    options=[
                                                        {"label": city, "value": city}
                                                        for city in CITY_OPTIONS
                                                    ],
                                                    placeholder="全部縣市",
                                                    clearable=True,
                                                ),
                                            ],
                                            className="field",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("店名／簡介關鍵字", htmlFor="explorer-keyword"),
                                                dcc.Input(
                                                    id="explorer-keyword",
                                                    type="search",
                                                    placeholder="例如：客家、海鮮、景觀",
                                                    debounce=True,
                                                    className="text-input",
                                                ),
                                            ],
                                            className="field",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("菜色類型（可複選）", htmlFor="explorer-cuisines"),
                                                dcc.Dropdown(
                                                    id="explorer-cuisines",
                                                    options=CUISINE_OPTIONS,
                                                    value=[],
                                                    placeholder="全部類型",
                                                    multi=True,
                                                    clearable=True,
                                                ),
                                            ],
                                            className="field",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("選擇店家", htmlFor="restaurant-picker"),
                                                dcc.Dropdown(
                                                    id="restaurant-picker",
                                                    options=[],
                                                    value=None,
                                                    placeholder="請先使用搜尋條件",
                                                    clearable=False,
                                                    searchable=True,
                                                    disabled=True,
                                                ),
                                            ],
                                            className="field",
                                        ),
                                        html.P(
                                            "設定縣市、關鍵字或菜色類型後，才會載入符合條件的店家資料。",
                                            className="picker-hint",
                                        ),
                                    ],
                                    className="explorer-picker",
                                )
                            ],
                            className="panel explorer-toolbar",
                        ),
                        html.Section(
                            [
                                html.Article(
                                    [
                                        dcc.Loading(
                                            html.Div(id="restaurant-detail"),
                                            type="circle",
                                        )
                                    ],
                                    className="panel detail-panel",
                                ),
                                html.Article(
                                    [
                                        html.Div(
                                            [html.H2("店家位置"), html.P("地圖已聚焦至目前選定的店家")],
                                            className="section-heading",
                                        ),
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="detail-map",
                                                config={"displayModeBar": False},
                                            )
                                        ),
                                    ],
                                    className="panel detail-map-panel",
                                ),
                            ],
                            className="explorer-grid",
                            id="explorer-details",
                            style={"display": "none"},
                        ),
                    ],
                    id="explorer-tab-content",
                    style={"display": "none"},
                ),
                html.Div(
                    [
                        html.Section(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Label("預計用餐時間"),
                                                        html.Strong(id="planner-time-label"),
                                                    ],
                                                    className="slider-heading",
                                                ),
                                                dcc.RangeSlider(
                                                    id="planner-time",
                                                    min=0,
                                                    max=23.5,
                                                    step=0.5,
                                                    value=[11.5, 13.5],
                                                    marks={
                                                        0: "00:00",
                                                        6: "06:00",
                                                        12: "12:00",
                                                        18: "18:00",
                                                        23.5: "23:30",
                                                    },
                                                    tooltip={
                                                        "placement": "bottom",
                                                        "always_visible": False,
                                                    },
                                                    allowCross=False,
                                                    pushable=0.5,
                                                ),
                                                html.P(
                                                    "拖曳兩端選擇用餐區間；營業時段需完整涵蓋所選範圍。",
                                                    className="planner-hint",
                                                ),
                                            ],
                                            className="planner-slider",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("縣市", htmlFor="planner-city"),
                                                dcc.Dropdown(
                                                    id="planner-city",
                                                    options=[
                                                        {"label": city, "value": city}
                                                        for city in CITY_OPTIONS
                                                    ],
                                                    value=PLANNER_DEFAULT_CITY,
                                                    placeholder="請選擇縣市",
                                                    clearable=False,
                                                ),
                                            ],
                                            className="field",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("菜色類型（可複選）", htmlFor="planner-cuisines"),
                                                dcc.Dropdown(
                                                    id="planner-cuisines",
                                                    options=CUISINE_OPTIONS,
                                                    value=[],
                                                    placeholder="全部類型",
                                                    multi=True,
                                                    clearable=True,
                                                ),
                                                html.P(
                                                    "選擇多種類型時，符合任一類型即可列入結果。",
                                                    className="planner-hint",
                                                ),
                                            ],
                                            className="field",
                                        ),
                                    ],
                                    className="planner-controls",
                                )
                            ],
                            className="panel planner-toolbar",
                        ),
                        html.Section(
                            [
                                html.Div(
                                    [html.H2("符合規劃的餐廳"), html.P(id="planner-summary")],
                                    className="section-heading",
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            dcc.Loading(
                                                dcc.Graph(
                                                    id="planner-map",
                                                    config={"displayModeBar": False},
                                                )
                                            ),
                                            className="planner-map-wrap",
                                        ),
                                    ],
                                    className="planner-output-grid",
                                ),
                                html.Div(
                                    [
                                        html.H3("全部符合條件的店家"),
                                        html.P("所有結果完整展開，不限制顯示筆數。"),
                                    ],
                                    className="planner-list-heading",
                                ),
                                html.Div(id="planner-results", className="planner-results"),
                            ],
                            className="panel planner-results-panel",
                        ),
                    ],
                    id="planner-tab-content",
                    style={"display": "none"},
                ),
            ]
        ),
        html.Footer("資料來源：專案 datasets/RestaurantList.json｜本頁僅供功能展示"),
    ],
    className="app-shell",
)


# -----------------------------------------------------------------------------
# 分頁切換回呼：只切換顯示狀態，保留兩頁已載入的資料與操作狀態。
# -----------------------------------------------------------------------------
@callback(
    Output("overview-tab-content", "style"),
    Output("explorer-tab-content", "style"),
    Output("planner-tab-content", "style"),
    Input("view-tabs", "value"),
)
def switch_view(active_tab: str):
    """依目前選取的分頁顯示資料總覽、店家探索或餐廳規劃。"""
    if active_tab == "explorer":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}
    if active_tab == "planner":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}, {"display": "none"}


# -----------------------------------------------------------------------------
# 店家探索篩選回呼：縣市獨立選取後，只保留該縣市的店家選項。
# -----------------------------------------------------------------------------
@callback(
    Output("restaurant-picker", "options"),
    Output("restaurant-picker", "value"),
    Output("restaurant-picker", "disabled"),
    Input("explorer-city", "value"),
    Input("explorer-keyword", "value"),
    Input("explorer-cuisines", "value"),
    Input("navigate-restaurant-store", "data"),
    State("restaurant-picker", "value"),
)
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
        return [], None, True

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
    return options, selected_id, not bool(options)


# -----------------------------------------------------------------------------
# 規劃頁導覽回呼：點擊卡片按鈕後切換至店家探索並指定該店家。
# -----------------------------------------------------------------------------
@callback(
    Output("view-tabs", "value"),
    Output("explorer-city", "value"),
    Output("explorer-keyword", "value"),
    Output("explorer-cuisines", "value"),
    Output("navigate-restaurant-store", "data"),
    Input({"type": "planner-detail-button", "restaurant_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
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


# -----------------------------------------------------------------------------
# 店家探索回呼：選定店家後，同步更新基本資料、社群連結與單店地圖。
# -----------------------------------------------------------------------------
@callback(
    Output("restaurant-detail", "children"),
    Output("detail-map", "figure"),
    Output("explorer-details", "style"),
    Input("restaurant-picker", "value"),
)
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


# -----------------------------------------------------------------------------
# 餐廳規劃回呼：依用餐時間、縣市與多值菜色類型推薦可選店家。
# -----------------------------------------------------------------------------
@callback(
    Output("planner-time-label", "children"),
    Output("planner-summary", "children"),
    Output("planner-map", "figure"),
    Output("planner-results", "children"),
    Input("view-tabs", "value"),
    Input("planner-time", "value"),
    Input("planner-city", "value"),
    Input("planner-cuisines", "value"),
)
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
        build_cuisine_pie(filtered),
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
