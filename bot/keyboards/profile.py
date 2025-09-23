from aiogram.utils.keyboard import InlineKeyboardBuilder

ACTIVITY_MAP = {
    "sedentary":"Малоактивный","light":"Лёгкая активность","moderate":"Средняя активность",
    "high":"Высокая активность","athlete":"Спорт ежедневно",
}

def sex_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Мужской", callback_data="reg:sex:male")
    kb.button(text="Женский", callback_data="reg:sex:female")
    kb.adjust(2)
    return kb.as_markup()

def activity_kb(prefix="reg"):
    kb = InlineKeyboardBuilder()
    for code, title in ACTIVITY_MAP.items():
        kb.button(text=title, callback_data=f"{prefix}:activity:{code}")
    kb.adjust(1)
    return kb.as_markup()

def edit_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="Имя", callback_data="edit:first")
    kb.button(text="Фамилия", callback_data="edit:last")
    kb.button(text="Пол", callback_data="edit:sex")
    kb.button(text="Дата рождения", callback_data="edit:birth")
    kb.button(text="Рост", callback_data="edit:height")
    kb.button(text="Вес", callback_data="edit:weight")
    kb.button(text="Активность", callback_data="edit:activity")
    kb.button(text="⬅️ В меню", callback_data="menu:root")
    kb.adjust(2)
    return kb.as_markup()
