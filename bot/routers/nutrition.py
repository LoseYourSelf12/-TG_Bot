import re
from datetime import date
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.filters import Command

from db.users import get_user_by_tg
from db.nutrition import (
    ensure_meal, day_items, day_kcal, list_foods_page, food_by_id, 
    add_meal_item, add_food, month_days_with_meals, days_totals_for_month, 
    delete_last_item, clear_day, add_custom_meal_item, PAGE_SIZE
)
from keyboards.calendar import month_kb
from keyboards.common import main_menu
from services.parse import parse_grams_time
from services.calorie import mifflin_st_jeor, tdee

router = Router()

def legend_text():
    return ("Легенда:\n"
            "❌ — нет записей\n"
            "🟢 — в пределах ±10% от нормы\n"
            "🟠 — выше нормы >10%\n"
            "🔵 — ниже нормы >10%")

def day_menu(d:date):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить продукт", callback_data="nutri:foods:0")
    kb.button(text="✍️ Свой продукт", callback_data="nutri:custom")
    kb.button(text="📖 Справочник", callback_data="nutri:foods_view:0")
    kb.button(text="🗑 Удалить последнюю", callback_data="nutri:del:last")
    kb.button(text="🗑 Очистить день", callback_data="nutri:del:all")
    kb.button(text="⬅️ К календарю", callback_data=f"nutri:cal:{d.year}-{d.month}")
    kb.adjust(1)
    return kb.as_markup()


def foods_page_kb(rows, offset, total, back_cb="nutri:day:back"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"{r['name']} ({r['kcal_100g']} ккал)", callback_data=f"nutri:food:{r['id']}")
    prev_off = max(offset - PAGE_SIZE, 0)
    next_off = offset + PAGE_SIZE if offset + PAGE_SIZE < total else offset
    kb.adjust(1)
    kb.button(text="←", callback_data=f"nutri:foods:{prev_off}")
    kb.button(text="Назад", callback_data=back_cb)
    kb.button(text="→", callback_data=f"nutri:foods:{next_off}")
    kb.adjust(3)
    return kb.as_markup()

async def month_marks_for_user(tg_id:int, year:int, month:int) -> dict[int, str]:
    # норма пользователя (TDEE)
    u = await get_user_by_tg(tg_id)
    if not u:
        return {}
    if not all([u.get("sex"), u.get("birth_date"), u.get("height_cm"), u.get("weight_kg"), u.get("activity_level")]):
        # если не всё заполнено — отмечаем только «есть записи/нет»
        days = await month_days_with_meals(tg_id, year, month)
        return {d: "⭕" for d in days}  # мягкая пометка
    y, mo, d = u["birth_date"].year, u["birth_date"].month, u["birth_date"].day
    from datetime import date as _d
    today = _d.today()
    age = today.year - y - ((today.month, today.day) < (mo, d))
    bmr = mifflin_st_jeor(u["sex"], float(u["weight_kg"]), int(u["height_cm"]), age)
    norm = tdee(bmr, u["activity_level"])
    # суммы по дням
    totals = await days_totals_for_month(tg_id, year, month)
    marks = {}
    for day in range(1, 32):
        if day not in totals:
            continue
        total = totals[day]
        if total <= 0.0:
            marks[day] = "❌"
            continue
        ratio = total / norm if norm > 0 else 0
        if 0.9 <= ratio <= 1.1:
            marks[day] = "🟢"
        elif ratio > 1.1:
            marks[day] = "🟠"
        else:
            marks[day] = "🔵"
    # дни без записей вообще — можно проставить ❌
    from calendar import monthrange
    _, last = monthrange(year, month)
    for day in range(1, last+1):
        if day not in marks:
            marks[day] = "❌"
    return marks

@router.callback_query(F.data == "nutri:menu")
async def nutri_menu(c: CallbackQuery):
    t = date.today()
    marks = await month_marks_for_user(c.from_user.id, t.year, t.month)
    await c.message.edit_text(legend_text() + "\n\nВыбери день:", reply_markup=month_kb(t.year, t.month, marks))
    await c.answer()

@router.callback_query(F.data.startswith("nutri:cal:"))
async def nutri_month(c: CallbackQuery):
    y, m = map(int, c.data.split(":")[2].split("-"))
    marks = await month_marks_for_user(c.from_user.id, y, m)
    await c.message.edit_text(legend_text() + "\n\nВыбери день:", reply_markup=month_kb(y, m, marks))
    await c.answer()

@router.callback_query(F.data.startswith("nutri:day:"))
async def nutri_day(c: CallbackQuery, state: FSMContext):
    d_iso = c.data.split(":")[-1]
    if d_iso == "back":
        # восстановим дату из state
        data = await state.get_data()
        d_iso = data.get("current_day_iso")
    d = date.fromisoformat(d_iso)
    await state.update_data(current_day_iso=d_iso)

    meal_id = await ensure_meal(c.from_user.id, d)
    await state.update_data(meal_id=meal_id)

    items = await day_items(meal_id)
    total = int(await day_kcal(meal_id))
    body = "\n".join([f"• {r['name']}: {r['grams']} г ≈ {r['kcal']} ккал" for r in items]) or "Записей пока нет."
    txt = f"<b>{d_iso}</b>\nВсего: {total} ккал\n\n{body}"
    await c.message.edit_text(txt, parse_mode="HTML", reply_markup=day_menu(d))
    await c.answer()

@router.callback_query(F.data.startswith("nutri:foods:"))
async def foods_pick(c: CallbackQuery, state: FSMContext):
    offset = int(c.data.split(":")[-1])
    rows, total = await list_foods_page(offset)
    if not rows:
        return await c.answer("Справочник пуст. Добавление доступно админам.", show_alert=True)
    await c.message.edit_text("Выбери продукт:", reply_markup=foods_page_kb(rows, offset, total))
    await c.answer()

@router.callback_query(F.data.startswith("nutri:food:"))
async def food_selected(c: CallbackQuery, state: FSMContext):
    food_id = int(c.data.split(":")[-1])
    await state.update_data(food_id=food_id)
    await c.message.edit_text("Введи: <b>граммы [час]</b> (например, 150 13 или просто 150)", parse_mode="HTML")
    await state.set_state(State("meal_grams_time"))
    await c.answer()

@router.message(State("meal_grams_time"))
async def grams_time_input(m: Message, state: FSMContext):
    grams, hh = parse_grams_time(m.text)
    data = await state.get_data()
    meal_id, food_id = data["meal_id"], data["food_id"]

    f = await food_by_id(food_id)
    kcal = round(grams * float(f["kcal_100g"]) / 100.0, 2)
    await add_meal_item(meal_id, food_id, grams, kcal)

    await state.set_state(None)

    # вернёмся к выбранному дню: покажем обновлённый список и кнопку «назад к календарю»
    from db.nutrition import day_items, day_kcal
    from datetime import date as _d

    d_iso = (await state.get_data()).get("current_day_iso")
    if not d_iso:
        d_iso = _d.today().isoformat()
        await state.update_data(current_day_iso=d_iso)
    d = _d.fromisoformat(d_iso)

    items = await day_items(meal_id)
    total = int(await day_kcal(meal_id))
    body = "\n".join([f"• {r['name']}: {r['grams']} г ≈ {r['kcal']} ккал" for r in items]) or "Записей пока нет."
    txt = f"✅ Добавлено: {f['name']} {grams} г ≈ {kcal} ккал\n\n<b>{d_iso}</b>\nВсего: {total} ккал\n\n{body}"
    await m.answer(txt, parse_mode="HTML", reply_markup=day_menu(d))

@router.callback_query(F.data == "nutri:del:last")
async def del_last(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    meal_id = data.get("meal_id")
    d_iso = data.get("current_day_iso")
    from datetime import date as _d
    d = _d.fromisoformat(d_iso)
    ok = await delete_last_item(meal_id)
    msg = "Удалено." if ok else "Нечего удалять."
    # перерисуем день
    items = await day_items(meal_id)
    total = int(await day_kcal(meal_id))
    body = "\n".join([f"• {r['name']}: {r['grams']} г ≈ {r['kcal']} ккал" for r in items]) or "Записей пока нет."
    txt = f"{msg}\n\n<b>{d_iso}</b>\nВсего: {total} ккал\n\n{body}"
    await c.message.edit_text(txt, parse_mode="HTML", reply_markup=day_menu(d))
    await c.answer()

@router.callback_query(F.data == "nutri:del:all")
async def del_all(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    meal_id = data.get("meal_id")
    d_iso = data.get("current_day_iso")
    from datetime import date as _d
    d = _d.fromisoformat(d_iso)
    n = await clear_day(meal_id)
    msg = f"Удалено позиций: {n}"
    items = await day_items(meal_id)
    total = int(await day_kcal(meal_id))
    body = "\n".join([f"• {r['name']}: {r['grams']} г ≈ {r['kcal']} ккал" for r in items]) or "Записей пока нет."
    txt = f"{msg}\n\n<b>{d_iso}</b>\nВсего: {total} ккал\n\n{body}"
    await c.message.edit_text(txt, parse_mode="HTML", reply_markup=day_menu(d))
    await c.answer()

def foods_view_page_kb(rows, offset, total):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(text=f"{r['name']} ({r['kcal_100g']} ккал)", callback_data="noop")
    kb.adjust(1)
    prev_off = max(offset - PAGE_SIZE, 0)
    next_off = offset + PAGE_SIZE if offset + PAGE_SIZE < total else offset
    kb.button(text="←", callback_data=f"nutri:foods_view:{prev_off}")
    kb.button(text="⬅️ Назад к дню", callback_data="nutri:day:back")
    kb.button(text="→", callback_data=f"nutri:foods_view:{next_off}")
    kb.adjust(3)
    return kb.as_markup()

@router.callback_query(F.data.startswith("nutri:foods_view:"))
async def foods_view(c: CallbackQuery, state: FSMContext):
    offset = int(c.data.split(":")[-1])
    rows, total = await list_foods_page(offset)
    if not rows:
        return await c.answer("Справочник пуст. Добавление доступно админам.", show_alert=True)
    await c.message.edit_text("Справочник продуктов (просмотр):", reply_markup=foods_view_page_kb(rows, offset, total))
    await c.answer()

@router.callback_query(F.data == "nutri:custom")
async def custom_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(State("meal_custom"))
    example = "Например: Бургер 250 180  (где 250 — ккал на 100 г, 180 — граммы)"
    await c.message.edit_text(
        "Введи: <b>название калории граммы</b>\n" + example,
        parse_mode="HTML"
    )
    await c.answer()

@router.message(State("meal_custom"))
async def custom_save(m: Message, state: FSMContext):
    # формат: "Название калории граммы"
    # имя может содержать пробелы; числа допускают запятую
    raw = (m.text or "").strip()
    # последний два «слова» — числа, всё перед ними — имя
    m2 = re.match(r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)$", raw)
    if not m2:
        return await m.answer("Неверный формат. Пример: Бургер 250 180")

    name = m2.group(1).strip()
    kcal100 = float(m2.group(2).replace(",", "."))
    grams = float(m2.group(3).replace(",", "."))

    data = await state.get_data()
    meal_id = data.get("meal_id")
    d_iso = data.get("current_day_iso")

    if not meal_id or not d_iso:
        return await m.answer("Сначала выбери день в календаре.")

    kcal = await add_custom_meal_item(meal_id, name, kcal100, grams)
    await state.set_state(None)

    # показать обновлённый день
    from datetime import date as _d
    d = _d.fromisoformat(d_iso)
    items = await day_items(meal_id)
    total = int(await day_kcal(meal_id))
    body = "\n".join([f"• {r['name']}: {r['grams']} г ≈ {r['kcal']} ккал" for r in items]) or "Записей пока нет."
    txt = (f"✅ Добавлено: {name} {grams} г (уд. {kcal100} ккал/100г) ≈ {kcal} ккал\n\n"
           f"<b>{d_iso}</b>\nВсего: {total} ккал\n\n{body}")
    await m.answer(txt, parse_mode="HTML", reply_markup=day_menu(d))


# --- админ: добавление продукта в справочник ---
@router.message(Command("addfood"))
async def add_food_cmd(m: Message):
    u = await get_user_by_tg(m.from_user.id)
    if not u or u.get("role") != "admin":
        return await m.answer("Недостаточно прав (нужно admin).")
    await m.answer("Формат: <название> ; <ккал на 100г>\nНапример: Творог 5% ; 121")

@router.message(F.text.regexp(r"^.+;\s*\d+(\.\d+)?$"))
async def add_food_parse(m: Message):
    u = await get_user_by_tg(m.from_user.id)
    if not u or u.get("role") != "admin":
        return
    name, kcal = m.text.split(";")
    await add_food(name.strip(), float(kcal.strip()))
    await m.answer(f"Добавлено: {name.strip()} ({float(kcal.strip())} ккал/100г)")
