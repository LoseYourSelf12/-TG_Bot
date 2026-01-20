from __future__ import annotations

import uuid
from datetime import date

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.meals import (
    build_day_meals_kb,
    build_meal_actions_kb,
    build_delete_confirm_kb,
    MealActionCb,
)
from app.bot.utils.panel import edit_panel_from_callback
from app.bot.utils.text import day_view_text, meal_details_text
from app.bot.states import AddMealFlow
from app.db.repo_meals import MealRepo
from aiogram.fsm.context import FSMContext


router = Router()


@router.callback_query(F.data.startswith("day:view:"))
async def open_day_view(cq: CallbackQuery, session: AsyncSession, user_id):
    _, _, day_str = cq.data.split(":")
    d = date.fromisoformat(day_str)

    repo = MealRepo(session)
    meals = await repo.list_meals_by_day(user_id, d)

    kb = build_day_meals_kb(d, meals, back_cb="menu:calendar_recent")
    await edit_panel_from_callback(cq, day_view_text(d, meals), kb)


@router.callback_query(MealActionCb.filter(F.action == "show"))
async def show_meal(cq: CallbackQuery, callback_data: MealActionCb, session: AsyncSession):
    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await cq.answer("Не найдено")
        return
    items = await repo.list_items(meal_id)
    photos = await repo.list_photos(meal_id)

    back_cb = f"day:view:{meal.meal_date.isoformat()}"
    kb = build_meal_actions_kb(meal_id, back_to_day_cb=back_cb)
    await edit_panel_from_callback(cq, meal_details_text(meal, items, photos), kb)


@router.callback_query(MealActionCb.filter(F.action == "delete"))
async def delete_meal_confirm(cq: CallbackQuery, callback_data: MealActionCb, session: AsyncSession):
    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await cq.answer("Не найдено")
        return
    back_cb = f"day:view:{meal.meal_date.isoformat()}"
    kb = build_delete_confirm_kb(meal_id, back_to_day_cb=back_cb)
    await edit_panel_from_callback(cq, "Точно удалить прием пищи? Это действие необратимо.", kb)


@router.callback_query(MealActionCb.filter(F.action == "delete_confirm"))
async def delete_meal(cq: CallbackQuery, callback_data: MealActionCb, session: AsyncSession, user_id):
    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await cq.answer("Не найдено")
        return

    day = meal.meal_date
    await repo.delete_meal(meal_id)

    meals = await repo.list_meals_by_day(user_id, day)
    kb = build_day_meals_kb(day, meals, back_cb="menu:calendar_recent")
    await edit_panel_from_callback(cq, "Удалено ✅\n\n" + day_view_text(day, meals), kb)


@router.callback_query(MealActionCb.filter(F.action == "edit"))
async def edit_meal_start(cq: CallbackQuery, callback_data: MealActionCb, state: FSMContext, session: AsyncSession):
    """
    Редактирование = создание новой записи, удаление старой только в конце.
    """
    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await cq.answer("Не найдено")
        return

    await state.update_data(meal_date=meal.meal_date, replace_meal_id=str(meal_id))
    await state.set_state(AddMealFlow.picking_time)

    from app.bot.keyboards.time_picker import build_time_picker
    from app.bot.utils.dates import now_in_tz
    from app.bot.utils.text import pick_time_text

    # profile middleware обычно даст TZ через state не нужно; здесь возьмем МСК как fallback
    now = now_in_tz("Europe/Moscow")
    await edit_panel_from_callback(cq, pick_time_text(meal.meal_date), build_time_picker(now))
