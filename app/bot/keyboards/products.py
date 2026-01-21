from __future__ import annotations

import uuid
from typing import List, Optional

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.utils.ids import uuid_to_short
from app.db.repo_products import RankedCandidate


class ProductPickCb(CallbackData, prefix="pp"):
    item: str   # short uuid
    prod: str   # short uuid


class ProductActionCb(CallbackData, prefix="pa"):
    item: str
    action: str  # "skip" | "back"


class ProductPageCb(CallbackData, prefix="pg"):
    item: str
    page: int


def build_product_candidates_kb(
    *,
    item_id: uuid.UUID,
    candidates: List[RankedCandidate],
    selected_product_id: Optional[uuid.UUID],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    item_short = uuid_to_short(item_id)
    selected_short = uuid_to_short(selected_product_id) if selected_product_id else None

    for c in candidates:
        c_short = uuid_to_short(c.product_id)

        # bucket: 0 exact, 1 name, 2 synonym
        bucket_prefix = "🎯 " if c.bucket == 0 else ("🔎 " if c.bucket == 1 else "🔁 ")
        chosen_prefix = "✅ " if (selected_short and c_short == selected_short) else ""
        label = (chosen_prefix + bucket_prefix + c.name)[:60]

        b.button(
            text=label,
            callback_data=ProductPickCb(item=item_short, prod=c_short).pack(),
        )

    # Навигация страниц
    if total_pages > 1:
        nav = InlineKeyboardBuilder()
        nav.button(text="◀️", callback_data=ProductPageCb(item=item_short, page=max(1, page - 1)).pack())
        nav.button(text=f"{page}/{total_pages}", callback_data="noop:header")
        nav.button(text="▶️", callback_data=ProductPageCb(item=item_short, page=min(total_pages, page + 1)).pack())
        b.row(*nav.as_markup().inline_keyboard[0])

    b.button(text="🚫 Без привязки", callback_data=ProductActionCb(item=item_short, action="skip").pack())
    b.button(text="⬅️ Назад", callback_data=ProductActionCb(item=item_short, action="back").pack())
    b.adjust(1)
    return b.as_markup()
