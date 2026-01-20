from __future__ import annotations

import uuid
from typing import List

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repo_products import ProductCandidate


class ProductPickCb(CallbackData, prefix="prodpick"):
    item_id: str  # uuid
    product_id: str  # uuid


class ProductActionCb(CallbackData, prefix="prodact"):
    item_id: str
    action: str  # "skip" | "back" | "pick_again"


def build_product_candidates_kb(item_id: uuid.UUID, candidates: List[ProductCandidate]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    for c in candidates:
        prefix = "🔁 " if c.source == "synonym" else ""
        # Чтобы кнопка была не гигантской
        label = (prefix + c.name)[:60]
        b.button(
            text=label,
            callback_data=ProductPickCb(item_id=str(item_id), product_id=str(c.product_id)).pack(),
        )

    b.button(text="🚫 Без привязки", callback_data=ProductActionCb(item_id=str(item_id), action="skip").pack())
    b.button(text="⬅️ Назад", callback_data=ProductActionCb(item_id=str(item_id), action="back").pack())
    b.adjust(1)
    return b.as_markup()
