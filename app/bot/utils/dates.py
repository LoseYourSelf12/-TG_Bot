from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo


def now_in_tz(timezone_iana: str) -> datetime:
    return datetime.now(tz=ZoneInfo(timezone_iana))


def today_in_tz(timezone_iana: str) -> date:
    return now_in_tz(timezone_iana).date()


def clamp_add_range(today: date) -> tuple[date, date]:
    """
    Для режима добавления: можно выбирать даты в диапазоне [today-30; today]
    """
    return today - timedelta(days=30), today


def add_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """
    delta может быть -1/+1
    """
    m = month + delta
    y = year
    if m == 0:
        y -= 1
        m = 12
    elif m == 13:
        y += 1
        m = 1
    return y, m
