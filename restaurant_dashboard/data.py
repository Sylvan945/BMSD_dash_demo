"""讀取與整理餐廳資料，建立各頁共用的篩選選項。"""

import json
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from .config import DATA_FILE, SERVICE_TIME_FILE, CUISINE_LABELS
from .time_utils import parse_time_ranges

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
