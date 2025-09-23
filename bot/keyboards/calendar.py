import calendar
from aiogram.utils.keyboard import InlineKeyboardBuilder

def month_kb(year:int, month:int, marks:set[int]|None=None):
    """
    marks: набор чисел дней (1..31), которые нужно пометить (есть записи).
    Мы добавим к номеру дня маленькую точку •
    """
    marks = marks or set()
    kb = InlineKeyboardBuilder()

    # Заголовок месяца (одна неактивная кнопка)
    kb.button(text=f"{calendar.month_name[month]} {year}", callback_data="noop")
    kb.adjust(1)

    # Сетка дней без строки Mo..Su
    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        for d in week:
            if d.month != month:
                kb.button(text=" ", callback_data="noop")
            else:
                label = f"{d.day}✅" if d.day in marks else f"{d.day}"
                kb.button(text=label, callback_data=f"nutri:day:{d.isoformat()}")
        kb.adjust(7)

    # Навигация по месяцам и выход в меню
    prev_y, prev_m = (year-1, 12) if month==1 else (year, month-1)
    next_y, next_m = (year+1, 1)  if month==12 else (year, month+1)
    kb.button(text="◀️", callback_data=f"nutri:cal:{prev_y}-{prev_m}")
    kb.button(text="⬅️ В меню", callback_data="menu:root")
    kb.button(text="▶️", callback_data=f"nutri:cal:{next_y}-{next_m}")
    kb.adjust(3)
    return kb.as_markup()
