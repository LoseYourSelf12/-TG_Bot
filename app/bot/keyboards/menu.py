from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🍽 Добавить прием пищи", callback_data="menu:add")
    b.button(text="📅 Календарь (дни)", callback_data="menu:calendar_recent")
    b.button(text="📊 Статистика", callback_data="menu:stats")
    if is_admin:
        b.button(text="🛠 Справочник", callback_data="admin_products:list:1")
    b.button(text="⚙️ Профиль (скоро)", callback_data="menu:profile")
    b.adjust(1)
    return b.as_markup()
