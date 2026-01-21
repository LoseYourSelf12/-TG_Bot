from __future__ import annotations

import uuid
from datetime import date

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
# from aiogram.exceptions import SkipHandler

from app.bot.keyboards.meals import (
    build_day_meals_kb,
    build_meal_actions_kb,
    build_delete_confirm_kb,
    MealActionCb,
)
from app.bot.keyboards.calendar import CalendarPickCb, CalendarMode
from app.bot.utils.panel import edit_panel_from_callback
from app.bot.utils.text import day_view_text, meal_details_text, meal_details_text_view
from app.bot.states import AddMealFlow
from app.db.repo_meals import MealRepo


router = Router()


@router.callback_query(F.data.startswith("day:view:"))
async def open_day_view(cq: CallbackQuery, session: AsyncSession, user_id, state: FSMContext):
    _, _, day_str = cq.data.split(":")
    d = date.fromisoformat(day_str)

    data = await state.get_data()
    back_cb = data.get("day_back_cb") or "menu:calendar_recent"

    repo = MealRepo(session)
    meals = await repo.list_meals_by_day(user_id, d)

    kb = build_day_meals_kb(d, meals, back_cb=back_cb)
    await edit_panel_from_callback(cq, day_view_text(d, meals), kb)


@router.callback_query(CalendarPickCb.filter(F.mode.in_([CalendarMode.ADD.value, CalendarMode.VIEW.value])))
async def open_day_from_calendar(
    cq: CallbackQuery,
    callback_data: CalendarPickCb,
    session: AsyncSession,
    user_id,
    state: FSMContext,
):
    d = date(callback_data.year, callback_data.month, callback_data.day)

    if callback_data.mode == CalendarMode.ADD.value:
        await state.update_data(day_back_cb=f"menu:open_month_add:{callback_data.year}:{callback_data.month}")
    else:
        await state.update_data(day_back_cb=f"menu:open_month_view:{callback_data.year}:{callback_data.month}")

    repo = MealRepo(session)
    meals = await repo.list_meals_by_day(user_id, d)

    kb = build_day_meals_kb(d, meals, back_cb=(await state.get_data())["day_back_cb"])
    await edit_panel_from_callback(cq, day_view_text(d, meals), kb)


@router.callback_query(MealActionCb.filter(F.action == "show"))
async def show_meal(cq: CallbackQuery, callback_data: MealActionCb, session: AsyncSession, state: FSMContext):
    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await cq.answer("Не найдено")
        return

    items = await repo.list_items_view(meal_id)
    photos = await repo.list_photos(meal_id)

    back_cb = f"day:view:{meal.meal_date.isoformat()}"
    kb = build_meal_actions_kb(meal_id, back_to_day_cb=back_cb, photos_count=len(photos))
    await edit_panel_from_callback(cq, meal_details_text_view(meal, items, photos), kb)


@router.callback_query(MealActionCb.filter(F.action == "photos"))
async def send_meal_photos(cq: CallbackQuery, callback_data: MealActionCb, session: AsyncSession):
    """
    Отправляем фото приёма пищи в чат.
    Используем tg_file_id (быстро, без диска). Если захочешь — можно fallback на local_path.
    """
    from aiogram.types import InputMediaPhoto

    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    photos = await repo.list_photos(meal_id)

    if not photos:
        await cq.answer("Фото нет", show_alert=True)
        return

    # Telegram media group: максимум 10 элементов
    chunks = [photos[i:i+10] for i in range(0, len(photos), 10)]
    for chunk in chunks:
        media = []
        for p in chunk:
            media.append(InputMediaPhoto(media=p.tg_file_id))
        await cq.bot.send_media_group(chat_id=cq.message.chat.id, media=media)

    await cq.answer("Фото отправлены ✅")


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
async def edit_meal_start(cq: CallbackQuery, callback_data: MealActionCb, state: FSMContext, session: AsyncSession, profile):
    meal_id = uuid.UUID(callback_data.meal_id)
    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await cq.answer("Не найдено")
        return

    # редактирование = создать новое, удалить старое на финале
    await state.update_data(meal_date=meal.meal_date, replace_meal_id=str(meal_id), return_to=f"day:view:{meal.meal_date.isoformat()}")
    await state.set_state(AddMealFlow.picking_time)

    from app.bot.keyboards.time_picker import build_time_picker
    from app.bot.utils.dates import now_in_tz
    from app.bot.utils.text import pick_time_text

    now = now_in_tz(profile.timezone_iana)
    await edit_panel_from_callback(cq, pick_time_text(meal.meal_date), build_time_picker(now))
