"""排行榜、餐廳分布地圖、單店地圖與菜色比例圖。"""

from collections import Counter

import pandas as pd
import plotly.express as px

from .config import CUISINE_LABELS

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
