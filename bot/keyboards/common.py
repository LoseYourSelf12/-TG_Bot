from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Мой профиль", callback_data="menu:profile")
    kb.button(text="✏️ Изменить параметры", callback_data="menu:edit")
    kb.button(text="🍽 Питание", callback_data="nutri:menu")
    kb.button(text="🔔 Напоминания", callback_data="rem:root")   # ← добавили
    kb.adjust(1)
    return kb.as_markup()

def back_to_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:root")
    return kb.as_markup()
