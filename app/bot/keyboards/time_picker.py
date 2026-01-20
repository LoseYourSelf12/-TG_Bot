from __future__ import annotations

from datetime import datetime, time, timedelta

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class TimePickCb(CallbackData, prefix="timepick"):
    hh: int
    mm: int


class TimeActionCb(CallbackData, prefix="timeact"):
    action: str  # "custom" | "back"


def _floor_to_15(dt: datetime) -> datetime:
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)


def build_time_picker(now: datetime) -> InlineKeyboardMarkup:
    base = _floor_to_15(now)
    t1 = base.time()
    t2 = (base - timedelta(minutes=15)).time()
    t3 = (base - timedelta(minutes=30)).time()

    b = InlineKeyboardBuilder()
    for t in [t1, t2, t3]:
        b.button(text=t.strftime("%H:%M"), callback_data=TimePickCb(hh=t.hour, mm=t.minute).pack())

    b.button(text="⌨️ Свое время", callback_data=TimeActionCb(action="custom").pack())
    b.button(text="⬅️ Назад", callback_data=TimeActionCb(action="back").pack())
    b.adjust(3, 1, 1)
    return b.as_markup()
