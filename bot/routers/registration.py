import os
from datetime import date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db.users import upsert_user_profile
from keyboards.profile import sex_kb, activity_kb
from keyboards.common import main_menu

router = Router()
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Europe/Moscow")

class Reg(StatesGroup):
    sex = State()
    birth = State()
    height = State()
    weight = State()
    first = State()
    last = State()
    activity = State()

@router.message(Command("register"))
async def start_reg(m: Message, state: FSMContext):
    await state.set_state(Reg.first)
    await m.answer("Введи имя (можно пропустить, отправив '-'):")

@router.message(Reg.first)
async def reg_first(m: Message, state: FSMContext):
    first = None if m.text.strip() == "-" else m.text.strip()
    await state.update_data(first_name=first)
    await state.set_state(Reg.last)
    await m.answer("Введи фамилию (можно '-'):")

@router.message(Reg.last)
async def reg_last(m: Message, state: FSMContext):
    last = None if m.text.strip() == "-" else m.text.strip()
    await state.update_data(last_name=last)
    await state.set_state(Reg.sex)
    await m.answer("Выбери пол:", reply_markup=sex_kb())

@router.callback_query(Reg.sex, F.data.startswith("reg:sex:"))
async def reg_sex(c: CallbackQuery, state: FSMContext):
    sex = c.data.split(":")[-1]
    await state.update_data(sex=sex)
    await state.set_state(Reg.birth)
    await c.message.edit_text("Дата рождения (ГГГГ-ММ-ДД):")
    await c.answer()

@router.message(Reg.birth)
async def reg_birth(m: Message, state: FSMContext):
    await state.update_data(birth=m.text.strip())
    await state.set_state(Reg.height)
    await m.answer("Рост в см:")

@router.message(Reg.height, F.text.regexp(r"^\d{2,3}$"))
async def reg_height(m: Message, state: FSMContext):
    await state.update_data(height_cm=int(m.text))
    await state.set_state(Reg.weight)
    await m.answer("Вес в кг (например, 81.5):")

@router.message(Reg.weight)
async def reg_weight(m: Message, state: FSMContext):
    txt = m.text.replace(",", ".").strip()
    await state.update_data(weight_kg=float(txt))
    await state.set_state(Reg.activity)
    await m.answer("Выбери уровень активности:", reply_markup=activity_kb("reg"))

@router.callback_query(Reg.activity, F.data.startswith("reg:activity:"))
async def reg_activity(c: CallbackQuery, state: FSMContext):
    activity = c.data.split(":")[-1]
    data = await state.get_data()
    await upsert_user_profile(
        tg_id=c.from_user.id, username=c.from_user.username, tz=DEFAULT_TZ,
        sex=data["sex"], birth=data["birth"], height_cm=data["height_cm"],
        weight_kg=data["weight_kg"], activity=activity,
        first_name=data.get("first_name"), last_name=data.get("last_name")
    )
    await state.clear()
    await c.message.edit_text("Регистрация завершена ✅", reply_markup=main_menu())
    await c.answer()
