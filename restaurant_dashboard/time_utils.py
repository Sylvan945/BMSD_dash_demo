"""營業時間解析、用餐時段比對與時間文字格式化。"""

import re

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
