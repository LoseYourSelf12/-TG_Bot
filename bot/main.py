import asyncio, os, logging
from datetime import date

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder

import psycopg
from psycopg.rows import dict_row

API_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Europe/Moscow")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("bot")

router = Router()

# ---------- DB ----------
async def get_conn():
    return await psycopg.AsyncConnection.connect(
        os.getenv("PG_DSN_NATIVE", "dbname=app user=app password=app host=postgres port=5432"),
        row_factory=dict_row,
    )

async def get_user(tg_id: int):
    async with await get_conn() as conn:
        cur = await conn.execute("select * from users where tg_id=%s", (tg_id,))
        return await cur.fetchone()

# ---------- FSM ----------
class Reg(StatesGroup):
    sex = State()       # инлайн
    birth = State()     # текст
    height = State()    # текст
    weight = State()    # текст
    activity = State()  # инлайн

class Edit(StatesGroup):
    birth = State()
    height = State()
    weight = State()

# ---------- Helpers ----------
ACTIVITY_MAP = {
    "sedentary": "Малоактивный",
    "light": "Лёгкая активность",
    "moderate": "Средняя активность",
    "high": "Высокая активность",
    "athlete": "Спорт ежедневно",
}

def mifflin_st_jeor(sex: str, weight: float, height_cm: int, age: int) -> float:
    base = 10 * weight + 6.25 * height_cm - 5 * age
    return base + (5 if sex == "male" else -161)

def tdee(bmr: float, activity: str) -> float:
    factors = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725, "athlete": 1.9}
    return bmr * factors.get(activity, 1.2)

def kb_sex():
    kb = InlineKeyboardBuilder()
    kb.button(text="Мужской", callback_data="reg:sex:male")
    kb.button(text="Женский", callback_data="reg:sex:female")
    kb.adjust(2)
    return kb.as_markup()

def kb_activity(prefix: str = "reg"):
    kb = InlineKeyboardBuilder()
    for code, title in ACTIVITY_MAP.items():
        kb.button(text=title, callback_data=f"{prefix}:activity:{code}")
    kb.adjust(1)
    return kb.as_markup()

def kb_main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Мой профиль", callback_data="menu:profile")
    kb.button(text="✏️ Изменить параметры", callback_data="menu:edit")
    kb.adjust(1)
    return kb.as_markup()

def kb_edit_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="Пол", callback_data="edit:sex")
    kb.button(text="Дата рождения", callback_data="edit:birth")
    kb.button(text="Рост", callback_data="edit:height")
    kb.button(text="Вес", callback_data="edit:weight")
    kb.button(text="Активность", callback_data="edit:activity")
    kb.button(text="⬅️ В меню", callback_data="menu:root")
    kb.adjust(2)
    return kb.as_markup()

# ---------- /start & /menu ----------
@router.message(CommandStart())
async def on_start(m: Message):
    await m.answer("Привет! Я помогу вести питание/тренировки/сон. Жми меню ниже.", reply_markup=kb_main_menu())

@router.message(Command("menu"))
async def on_menu(m: Message):
    await m.answer("Главное меню:", reply_markup=kb_main_menu())

# ---------- Меню ----------
@router.callback_query(F.data == "menu:root")
async def cb_menu_root(c: CallbackQuery):
    await c.message.edit_text("Главное меню:", reply_markup=kb_main_menu())
    await c.answer()

@router.callback_query(F.data == "menu:profile")
async def cb_profile(c: CallbackQuery):
    u = await get_user(c.from_user.id)
    if not u:
        await c.message.edit_text("Ты ещё не зарегистрирован. Нажми /register")
        return await c.answer()

    if all([u.get("sex"), u.get("birth_date"), u.get("height_cm"), u.get("weight_kg"), u.get("activity_level")]):
        y, mo, d = u["birth_date"].year, u["birth_date"].month, u["birth_date"].day
        today = date.today()
        age = today.year - y - ((today.month, today.day) < (mo, d))
        bmr = int(mifflin_st_jeor(u["sex"], float(u["weight_kg"]), int(u["height_cm"]), age))
        daily = int(tdee(bmr, u["activity_level"]))
    else:
        bmr = daily = None

    txt = (
        "<b>Твой профиль</b>\n"
        f"Пол: {('Мужской' if u.get('sex')=='male' else 'Женский') if u.get('sex') else '—'}\n"
        f"Дата рождения: {u.get('birth_date') or '—'}\n"
        f"Рост: {u.get('height_cm') or '—'} см\n"
        f"Вес: {u.get('weight_kg') or '—'} кг\n"
        f"Активность: {ACTIVITY_MAP.get(u.get('activity_level'), '—')}\n"
        f"Калории (BMR): {bmr if bmr else '—'}\n"
        f"Ориентир (TDEE): {daily if daily else '—'}\n"
    )
    await c.message.edit_text(txt, reply_markup=kb_edit_menu(), parse_mode="HTML")
    await c.answer()

@router.callback_query(F.data == "menu:edit")
async def cb_edit(c: CallbackQuery):
    await c.message.edit_text("Что редактируем?", reply_markup=kb_edit_menu())
    await c.answer()

# ---------- Регистрация ----------
@router.message(Command("register"))
async def start_reg(m: Message, state: FSMContext):
    await state.set_state(Reg.sex)
    await m.answer("Выбери пол:", reply_markup=kb_sex())

@router.callback_query(Reg.sex, F.data.startswith("reg:sex:"))
async def reg_sex(c: CallbackQuery, state: FSMContext):
    sex = c.data.split(":")[-1]
    await state.update_data(sex=sex)
    await state.set_state(Reg.birth)
    await c.message.edit_text("Дата рождения (ГГГГ-ММ-ДД):")
    await c.answer()

@router.message(Reg.birth)
async def reg_birth(m: Message, state: FSMContext):
    await state.update_data(birth=m.text)
    await state.set_state(Reg.height)
    await m.answer("Рост в см:")

@router.message(Reg.height, F.text.regexp(r"^\d{2,3}$"))
async def reg_height(m: Message, state: FSMContext):
    await state.update_data(height_cm=int(m.text))
    await state.set_state(Reg.weight)
    await m.answer("Вес в кг:")

@router.message(Reg.weight, F.text.regexp(r"^\d{2,3}(\.\d)?$"))
async def reg_weight(m: Message, state: FSMContext):
    await state.update_data(weight_kg=float(m.text))
    await state.set_state(Reg.activity)
    await m.answer("Выбери уровень активности:", reply_markup=kb_activity("reg"))

@router.callback_query(Reg.activity, F.data.startswith("reg:activity:"))
async def reg_activity(c: CallbackQuery, state: FSMContext):
    activity = c.data.split(":")[-1]
    data = await state.update_data(activity=activity)

    y, mo, d = map(int, data["birth"].split("-"))
    today = date.today()
    age = today.year - y - ((today.month, today.day) < (mo, d))
    bmr = mifflin_st_jeor(data["sex"], data["weight_kg"], data["height_cm"], age)
    daily = round(tdee(bmr, activity))

    async with await get_conn() as conn:
        await conn.execute(
            """
            insert into users(tg_id, username, tz, sex, birth_date, height_cm, weight_kg, activity_level, tier)
            values(%s,%s,%s,%s,%s,%s,%s,%s,'basic')
            on conflict (tg_id) do update set
              sex=excluded.sex, birth_date=excluded.birth_date, height_cm=excluded.height_cm,
              weight_kg=excluded.weight_kg, activity_level=excluded.activity_level
            """,
            (
                c.from_user.id,
                c.from_user.username,
                DEFAULT_TZ,
                data["sex"],
                data["birth"],
                data["height_cm"],
                data["weight_kg"],
                activity,
            ),
        )

    await state.clear()
    await c.message.edit_text(
        f"Готово! BMR ≈ {int(bmr)} ккал/день, ориентир по активности ≈ {daily} ккал/день.",
        reply_markup=kb_main_menu()
    )
    await c.answer()

# ---------- Редактирование профиля ----------
@router.callback_query(F.data == "edit:sex")
async def edit_sex(c: CallbackQuery):
    await c.message.edit_text("Выбери пол:", reply_markup=kb_sex())
    await c.answer()

@router.callback_query(F.data.startswith("reg:sex:"))
async def edit_sex_set(c: CallbackQuery):
    sex = c.data.split(":")[-1]
    async with await get_conn() as conn:
        await conn.execute("update users set sex=%s where tg_id=%s", (sex, c.from_user.id))
    await cb_profile(c)

@router.callback_query(F.data == "edit:activity")
async def edit_activity(c: CallbackQuery):
    await c.message.edit_text("Выбери активность:", reply_markup=kb_activity("edit"))
    await c.answer()

@router.callback_query(F.data.startswith("edit:activity:"))
async def edit_activity_set(c: CallbackQuery):
    activity = c.data.split(":")[-1]
    async with await get_conn() as conn:
        await conn.execute("update users set activity_level=%s where tg_id=%s", (activity, c.from_user.id))
    await cb_profile(c)

@router.callback_query(F.data == "edit:birth")
async def edit_birth(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.birth)
    await c.message.edit_text("Введи дату рождения (ГГГГ-ММ-ДД):")
    await c.answer()

@router.message(Edit.birth)
async def edit_birth_set(m: Message, state: FSMContext):
    async with await get_conn() as conn:
        await conn.execute("update users set birth_date=%s where tg_id=%s", (m.text, m.from_user.id))
    await state.clear()
    await m.answer("Обновлено.", reply_markup=kb_main_menu())

@router.callback_query(F.data == "edit:height")
async def edit_height(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.height)
    await c.message.edit_text("Введи рост в см:")
    await c.answer()

@router.message(Edit.height, F.text.regexp(r"^\d{2,3}$"))
async def edit_height_set(m: Message, state: FSMContext):
    async with await get_conn() as conn:
        await conn.execute("update users set height_cm=%s where tg_id=%s", (int(m.text), m.from_user.id))
    await state.clear()
    await m.answer("Обновлено.", reply_markup=kb_main_menu())

@router.callback_query(F.data == "edit:weight")
async def edit_weight(c: CallbackQuery, state: FSMContext):
    await state.set_state(Edit.weight)
    await c.message.edit_text("Введи вес в кг (например, 81.5):")
    await c.answer()

@router.message(Edit.weight, F.text.regexp(r"^\\d{2,3}(\\.\\d)?$"))
async def edit_weight_set(m: Message, state: FSMContext):
    async with await get_conn() as conn:
        await conn.execute("update users set weight_kg=%s where tg_id=%s", (float(m.text), m.from_user.id))
    await state.clear()
    await m.answer("Обновлено.", reply_markup=kb_main_menu())

# ---------- boot ----------
async def main():
    if not API_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в окружении")

    storage = RedisStorage.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        key_builder=DefaultKeyBuilder(with_bot_id=True),
    )
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    bot = Bot(API_TOKEN)
    log.info("Starting polling…")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])  # MVP

if __name__ == "__main__":
    asyncio.run(main())
