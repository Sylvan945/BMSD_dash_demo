"""共用摘要卡片、餐廳結果卡片與詳細資料欄位。"""

import pandas as pd
from dash import html

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
