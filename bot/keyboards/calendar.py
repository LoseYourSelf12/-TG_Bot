import calendar
from aiogram.utils.keyboard import InlineKeyboardBuilder

def month_kb(year:int, month:int, marks:dict[int, str]|None=None):
    """
    marks: {день: emoji}. Например {5: '🟢', 7:'❌'}
    """
    marks = marks or {}
    kb = InlineKeyboardBuilder()

    kb.button(text=f"{calendar.month_name[month]} {year}", callback_data="noop")
    kb.adjust(1)

    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        for d in week:
            if d.month != month:
                kb.button(text=" ", callback_data="noop")
            else:
                prefix = marks.get(d.day, "")
                label = f"{prefix}{d.day}" if prefix else f"{d.day}"
                kb.button(text=label, callback_data=f"nutri:day:{d.isoformat()}")
        kb.adjust(7)

    prev_y, prev_m = (year-1, 12) if month==1 else (year, month-1)
    next_y, next_m = (year+1, 1)  if month==12 else (year, month+1)
    kb.button(text="◀️", callback_data=f"nutri:cal:{prev_y}-{prev_m}")
    kb.button(text="⬅️ В меню", callback_data="menu:root")
    kb.button(text="▶️", callback_data=f"nutri:cal:{next_y}-{next_m}")
    kb.adjust(3)
    return kb.as_markup()
