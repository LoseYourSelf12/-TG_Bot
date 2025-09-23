from datetime import date
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db.users import get_user_by_tg, update_user_field
from services.calorie import mifflin_st_jeor, tdee
from db.nutrition import today_kcal
from keyboards.profile import ACTIVITY_MAP, edit_menu, sex_kb, activity_kb
from keyboards.common import main_menu

router = Router()

class Edit(StatesGroup):
    first = State()
    last = State()
    birth = State()
    height = State()
    weight = State()

@router.message(CommandStart())
async def start(m: Message):
    await m.answer("Привет! Главное меню:", reply_markup=main_menu())

@router.message(Command("menu"))
async def menu(m: Message):
    await m.answer("Главное меню:", reply_markup=main_menu())

@router.callback_query(F.data == "menu:root")
async def menu_root(c: CallbackQuery):
    await c.message.edit_text("Главное меню:", reply_markup=main_menu())
    await c.answer()

@router.callback_query(F.data == "menu:profile")
async def profile_view(c: CallbackQuery):
    u = await get_user_by_tg(c.from_user.id)
    if not u:
        await c.message.edit_text("Ты ещё не зарегистрирован. Нажми /register")
        return await c.answer()

    # расчет BMR/TDEE
    if all([u.get("sex"), u.get("birth_date"), u.get("height_cm"), u.get("weight_kg"), u.get("activity_level")]):
        y, mo, d = u["birth_date"].year, u["birth_date"].month, u["birth_date"].day
        today = date.today()
        age = today.year - y - ((today.month, today.day) < (mo, d))
        bmr = int(mifflin_st_jeor(u["sex"], float(u["weight_kg"]), int(u["height_cm"]), age))
        daily = int(tdee(bmr, u["activity_level"]))
    else:
        bmr = daily = None

    today_total = await today_kcal(c.from_user.id)

    txt = (
        "<b>Профиль</b>\n"
        f"Имя: {u.get('display_name') or 'пользователь'}\n"
        f"Пол: {('Мужской' if u.get('sex')=='male' else 'Женский') if u.get('sex') else '—'}\n"
        f"Дата рождения: {u.get('birth_date') or '—'}\n"
        f"Рост: {u.get('height_cm') or '—'} см\n"
        f"Вес: {u.get('weight_kg') or '—'} кг\n"
        f"Активность: {ACTIVITY_MAP.get(u.get('activity_level'), '—')}\n"
        f"Калории (BMR): {bmr if bmr else '—'}\n"
        f"Ориентир (TDEE): {daily if daily else '—'}\n"
        f"Сегодня потреблено: {today_total} ккал\n"
        f"Уровень доступа: {u.get('role')}\n"
    )
    await c.message.edit_text(txt, parse_mode="HTML", reply_markup=edit_menu())
    await c.answer()

@router.callback_query(F.data == "menu:edit")
async def menu_edit(c: CallbackQuery):
    await c.message.edit_text("Что редактируем?", reply_markup=edit_menu())
    await c.answer()

# --- Имя/фамилия ---
@router.callback_query(F.data == "edit:first")
async def edit_first(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.first)
    await c.message.edit_text("Введи имя (или '-' чтобы очистить):")
    await c.answer()

@router.message(Edit.first)
async def edit_first_set(m: Message, state: FSMContext):
    txt = m.text.strip()
    val = None if txt == "-" else txt
    await update_user_field(m.from_user.id, "first_name", val)
    await update_user_field(m.from_user.id, "display_name", val or "пользователь")
    await state.clear()
    await m.answer("Обновлено.", reply_markup=main_menu())

@router.callback_query(F.data == "edit:last")
async def edit_last(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.last)
    await c.message.edit_text("Введи фамилию (или '-' чтобы очистить):")
    await c.answer()

@router.message(Edit.last)
async def edit_last_set(m: Message, state: FSMContext):
    txt = m.text.strip()
    val = None if txt == "-" else txt
    await update_user_field(m.from_user.id, "last_name", val)
    await state.clear()
    await m.answer("Обновлено.", reply_markup=main_menu())

# --- Пол/Активность (инлайн) ---
@router.callback_query(F.data == "edit:sex")
async def edit_sex(c: CallbackQuery):
    await c.message.edit_text("Выбери пол:", reply_markup=sex_kb())
    await c.answer()

@router.callback_query(F.data.startswith("reg:sex:"))
async def edit_sex_set(c: CallbackQuery):
    sex = c.data.split(":")[-1]
    await update_user_field(c.from_user.id, "sex", sex)
    await profile_view(c)

@router.callback_query(F.data == "edit:activity")
async def edit_act(c: CallbackQuery):
    await c.message.edit_text("Уровень активности:", reply_markup=activity_kb("edit"))
    await c.answer()

@router.callback_query(F.data.startswith("edit:activity:"))
async def edit_act_set(c: CallbackQuery):
    activity = c.data.split(":")[-1]
    await update_user_field(c.from_user.id, "activity_level", activity)
    await profile_view(c)

# --- ДР/рост/вес (текст) ---
@router.callback_query(F.data == "edit:birth")
async def edit_birth(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.birth)
    await c.message.edit_text("Дата рождения (ГГГГ-ММ-ДД):")
    await c.answer()

@router.message(Edit.birth)
async def edit_birth_set(m: Message, state: FSMContext):
    await update_user_field(m.from_user.id, "birth_date", m.text.strip())
    await state.clear()
    await m.answer("Обновлено.", reply_markup=main_menu())

@router.callback_query(F.data == "edit:height")
async def edit_height(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.height)
    await c.message.edit_text("Рост в см:")
    await c.answer()

@router.message(Edit.height)
async def edit_height_set(m: Message, state: FSMContext):
    await update_user_field(m.from_user.id, "height_cm", int(m.text.strip()))
    await state.clear()
    await m.answer("Обновлено.", reply_markup=main_menu())

@router.callback_query(F.data == "edit:weight")
async def edit_weight(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.weight)
    await c.message.edit_text("Введи вес в кг (например, 81.5):")
    await c.answer()

@router.message(Edit.weight)
async def edit_weight_set(m: Message, state: FSMContext):
    txt = (m.text or "").replace(",", ".").strip()
    import re
    if not re.fullmatch(r"\d{2,3}(\.\d{1,2})?", txt):
        return await m.answer("Некорректный формат. Пример: 81.5")
    await update_user_field(m.from_user.id, "weight_kg", float(txt))
    await state.clear()
    # сразу вернём профиль с пересчетом
    # «фейковый» cb для переиспользования отрисовки
    from aiogram.types import CallbackQuery
    fake = CallbackQuery(id="0", from_user=m.from_user, chat_instance="", message=await m.answer("Обновляю профиль..."))
    await profile_view(fake)

EditWeightExternal = State("Edit:weight")

@router.message(EditWeightExternal)
async def weight_from_reminder(m: Message, state: FSMContext):
    txt = (m.text or "").replace(",", ".").strip()
    import re
    if not re.fullmatch(r"\d{2,3}(\.\d{1,2})?", txt):
        return await m.answer("Некорректный формат. Пример: 81.5")
    await update_user_field(m.from_user.id, "weight_kg", float(txt))
    await state.clear()
    await m.answer("Вес обновлён.")