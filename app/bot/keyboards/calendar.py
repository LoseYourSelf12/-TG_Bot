from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Dict, Optional

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repo_meals import DayMark


class CalendarMode(StrEnum):
    ADD = "add"
    STATS = "stats"


class CalendarOpenCb(CallbackData, prefix="calopen"):
    mode: str  # CalendarMode
    year: int
    month: int


class CalendarNavCb(CallbackData, prefix="calnav"):
    mode: str
    year: int
    month: int
    direction: str  # "prev" | "next"


class CalendarPickCb(CallbackData, prefix="calpick"):
    mode: str
    year: int
    month: int
    day: int


class NoopCb(CallbackData, prefix="noop"):
    why: str


def _month_name_ru(month: int) -> str:
    names = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    return names[month - 1]


def build_month_calendar(
    *,
    mode: CalendarMode,
    year: int,
    month: int,
    marks: Dict[date, DayMark],
    min_date: Optional[date] = None,
    max_date: Optional[date] = None,
    back_cb: str = "menu:back",
    show_weekdays: bool = True,
) -> InlineKeyboardMarkup:
    """
    min_date/max_date: ограничения на кликабельные дни.
    Если день вне диапазона - callback -> noop.
    """
    import calendar

    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdayscalendar(year, month)

    b = InlineKeyboardBuilder()

    # Header row: month + nav
    title = f"{_month_name_ru(month)} {year}"
    b.row(
        # prev
        *[
            InlineKeyboardBuilder().button(
                text="◀️",
                callback_data=CalendarNavCb(mode=mode.value, year=year, month=month, direction="prev").pack(),
            ).as_markup().inline_keyboard[0][0],
            InlineKeyboardBuilder().button(text=title, callback_data=NoopCb(why="header").pack()).as_markup().inline_keyboard[0][0],
            InlineKeyboardBuilder().button(
                text="▶️",
                callback_data=CalendarNavCb(mode=mode.value, year=year, month=month, direction="next").pack(),
            ).as_markup().inline_keyboard[0][0],
        ]
    )

    if show_weekdays:
        for wd in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
            b.button(text=wd, callback_data=NoopCb(why="wd").pack())
        b.adjust(3, 7)

    # Days
    for week in weeks:
        row_btns = []
        for d in week:
            if d == 0:
                row_btns.append((" ", NoopCb(why="empty").pack()))
                continue

            day_dt = date(year, month, d)
            in_range = True
            if min_date and day_dt < min_date:
                in_range = False
            if max_date and day_dt > max_date:
                in_range = False

            mark = marks.get(day_dt)
            # Маркеры: ✅ если есть приемы, 📷 если фото
            label = str(d)
            if mark and mark.meals_count > 0:
                label += "✅"
            if mark and mark.photos_count > 0:
                label += "📷"

            cb = (
                CalendarPickCb(mode=mode.value, year=year, month=month, day=d).pack()
                if in_range
                else NoopCb(why="out_of_range").pack()
            )
            row_btns.append((label, cb))

        for text, cb in row_btns:
            b.button(text=text, callback_data=cb)

    b.adjust(3, 7, *([7] * len(weeks)))

    # Footer
    b.row(
        InlineKeyboardBuilder().button(text="⬅️ Назад", callback_data=back_cb).as_markup().inline_keyboard[0][0]
    )
    return b.as_markup()
