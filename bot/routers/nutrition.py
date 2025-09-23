from datetime import date
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.filters import Command

from db.users import get_user_by_tg
from db.nutrition import (
    ensure_meal, day_items, day_kcal, list_foods_page, food_by_id, 
    add_meal_item, add_food, month_days_with_meals, PAGE_SIZE
)
from keyboards.calendar import month_kb
from keyboards.common import main_menu
from services.parse import parse_grams_time

router = Router()

def day_menu(d:date):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить продукт", callback_data="nutri:foods:0")
    kb.button(text="📖 Справочник", callback_data="nutri:foods_view:0")
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

@router.callback_query(F.data == "nutri:menu")
async def nutri_menu(c: CallbackQuery):
    t = date.today()
    marks = await month_days_with_meals(c.from_user.id, t.year, t.month)
    await c.message.edit_text("Выбери день:", reply_markup=month_kb(t.year, t.month, marks))
    await c.answer()

@router.callback_query(F.data.startswith("nutri:cal:"))
async def nutri_month(c: CallbackQuery):
    y, m = map(int, c.data.split(":")[2].split("-"))
    marks = await month_days_with_meals(c.from_user.id, y, m)
    await c.message.edit_text("Выбери день:", reply_markup=month_kb(y, m, marks))
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

    # вычислим ккал по справочнику
    f = await food_by_id(food_id)
    kcal = round(grams * float(f["kcal_100g"]) / 100.0, 2)
    await add_meal_item(meal_id, food_id, grams, kcal)

    await state.set_state(None)
    # вернёмся к дню
    from aiogram.types import CallbackQuery
    fake = CallbackQuery(id="0", from_user=m.from_user, chat_instance="", message=await m.answer("Сохраняю..."))
    await nutri_day(fake, state)

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
