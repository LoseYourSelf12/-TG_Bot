from __future__ import annotations

import uuid
from datetime import date
from typing import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Meal


class DayOpenCb(CallbackData, prefix="dayopen"):
    day: str  # YYYY-MM-DD
    mode: str  # "add" | "stats" | "view"


class MealActionCb(CallbackData, prefix="mealact"):
    meal_id: str
    action: str  # "delete" | "delete_confirm" | "edit" | "show"


def build_day_meals_kb(day: date, meals: Iterable[Meal], back_cb: str = "menu:back") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for m in meals:
        label = f"🕒 {m.meal_time.strftime('%H:%M')}"
        b.button(text=label, callback_data=MealActionCb(meal_id=str(m.id), action="show").pack())

    b.button(text="➕ Добавить прием пищи", callback_data=f"day:add:{day.isoformat()}")
    b.button(text="⬅️ Назад", callback_data=back_cb)
    b.adjust(1)
    return b.as_markup()


def build_meal_actions_kb(meal_id: uuid.UUID, back_to_day_cb: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Редактировать", callback_data=MealActionCb(meal_id=str(meal_id), action="edit").pack())
    b.button(text="🗑 Удалить", callback_data=MealActionCb(meal_id=str(meal_id), action="delete").pack())
    b.button(text="⬅️ Назад", callback_data=back_to_day_cb)
    b.adjust(1)
    return b.as_markup()


def build_delete_confirm_kb(meal_id: uuid.UUID, back_to_day_cb: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, удалить", callback_data=MealActionCb(meal_id=str(meal_id), action="delete_confirm").pack())
    b.button(text="⬅️ Отмена", callback_data=back_to_day_cb)
    b.adjust(1)
    return b.as_markup()
