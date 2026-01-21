from __future__ import annotations

import uuid
from typing import List

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repo_products import ProductCandidate
from app.bot.utils.ids import uuid_to_short


class ProductPickCb(CallbackData, prefix="pp"):
    item: str   # short uuid
    prod: str   # short uuid


class ProductActionCb(CallbackData, prefix="pa"):
    item: str
    action: str  # "skip" | "back"


def build_product_candidates_kb(item_id: uuid.UUID, candidates: List[ProductCandidate]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    item_short = uuid_to_short(item_id)

    for c in candidates:
        prefix = "🔁 " if c.source == "synonym" else ""
        label = (prefix + c.name)[:60]
        b.button(
            text=label,
            callback_data=ProductPickCb(item=item_short, prod=uuid_to_short(c.product_id)).pack(),
        )

    b.button(text="🚫 Без привязки", callback_data=ProductActionCb(item=item_short, action="skip").pack())
    b.button(text="⬅️ Назад", callback_data=ProductActionCb(item=item_short, action="back").pack())
    b.adjust(1)
    return b.as_markup()
