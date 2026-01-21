from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.utils.ids import uuid_to_short


# ---- CallbackData (короткие префиксы) ----
class APListCb(CallbackData, prefix="apl"):
    page: int


class APOpenCb(CallbackData, prefix="apo"):
    pid: str  # short uuid
    page: int


class APAddCb(CallbackData, prefix="apa"):
    page: int


class APEditCb(CallbackData, prefix="ape"):
    pid: str
    page: int


class APDelAskCb(CallbackData, prefix="apd"):
    pid: str
    page: int


class APDelConfCb(CallbackData, prefix="apx"):
    pid: str
    page: int


class APMissAllCb(CallbackData, prefix="apm"):
    pid: str
    page: int


class APCancelAddCb(CallbackData, prefix="apca"):
    page: int


class APCancelEditCb(CallbackData, prefix="apce"):
    pid: str
    page: int


@dataclass(frozen=True)
class ProductRow:
    id: uuid.UUID
    name: str
    kcal_per_100g: float
    complete: bool


def products_list_kb(
    *,
    page: int,
    total_pages: int,
    total_count: int,
    rows: Iterable[ProductRow],
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    for r in rows:
        mark = "✅" if r.complete else "❌"
        b.button(
            text=f"{mark} {r.name} — {r.kcal_per_100g:.0f} ккал",
            callback_data=APOpenCb(pid=uuid_to_short(r.id), page=page).pack(),
        )

    nav = InlineKeyboardBuilder()
    nav.button(text="◀️", callback_data=APListCb(page=max(1, page - 1)).pack())
    nav.button(text=f"{page}/{max(1, total_pages)} • всего {total_count}", callback_data="noop:header")
    nav.button(text="▶️", callback_data=APListCb(page=min(total_pages, page + 1)).pack())
    b.row(*nav.as_markup().inline_keyboard[0])

    b.button(text="➕ Добавить продукт", callback_data=APAddCb(page=page).pack())
    b.button(text="⬅️ Назад", callback_data="menu:back")
    b.adjust(1)
    return b.as_markup()


def product_card_kb(product_id: uuid.UUID, back_page: int) -> InlineKeyboardMarkup:
    pid = uuid_to_short(product_id)
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Редактировать", callback_data=APEditCb(pid=pid, page=back_page).pack())
    b.button(text="🗑 Удалить", callback_data=APDelAskCb(pid=pid, page=back_page).pack())
    b.button(text="⬅️ Назад к списку", callback_data=APListCb(page=back_page).pack())
    b.adjust(1)
    return b.as_markup()


def product_delete_confirm_kb(product_id: uuid.UUID, back_page: int) -> InlineKeyboardMarkup:
    pid = uuid_to_short(product_id)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Да, удалить", callback_data=APDelConfCb(pid=pid, page=back_page).pack())
    b.button(text="⬅️ Отмена", callback_data=APOpenCb(pid=pid, page=back_page).pack())
    b.adjust(1)
    return b.as_markup()


def missing_synonyms_kb(product_id: uuid.UUID, back_page: int, missing_count: int) -> InlineKeyboardMarkup:
    pid = uuid_to_short(product_id)
    b = InlineKeyboardBuilder()
    b.button(
        text=f"➕ Добавить ВСЕ {missing_count} как продукты",
        callback_data=APMissAllCb(pid=pid, page=back_page).pack(),
    )
    b.button(text="⬅️ Назад к карточке", callback_data=APOpenCb(pid=pid, page=back_page).pack())
    b.adjust(1)
    return b.as_markup()


def input_add_kb(back_page: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=APCancelAddCb(page=back_page).pack())
    b.adjust(1)
    return b.as_markup()


def input_edit_kb(product_id: uuid.UUID, back_page: int) -> InlineKeyboardMarkup:
    pid = uuid_to_short(product_id)
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=APCancelEditCb(pid=pid, page=back_page).pack())
    b.adjust(1)
    return b.as_markup()
