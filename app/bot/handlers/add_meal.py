from __future__ import annotations

import uuid
from datetime import date, time

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import AddMealFlow
from app.bot.keyboards.time_picker import build_time_picker, TimePickCb, TimeActionCb
from app.bot.keyboards.products import build_product_candidates_kb, ProductPickCb, ProductActionCb
from app.bot.utils.dates import now_in_tz
from app.bot.utils.parse import parse_time_hhmm, snap_to_15, parse_items_csv
from app.bot.utils.panel import edit_panel_from_callback, ensure_panel
from app.bot.utils.text import (
    pick_time_text,
    enter_custom_time_text,
    enter_items_text,
    map_item_text,
    ask_grams_text,
)
from app.db.repo_meals import MealRepo
from app.db.repo_products import ProductRepo


router = Router()


# ========== entry points ==========
@router.callback_query(F.data.startswith("day:add:"))
async def day_add_meal(cq: CallbackQuery, state: FSMContext):
    # date already selected (from day view)
    _, _, day_str = cq.data.split(":")
    d = date.fromisoformat(day_str)
    await state.update_data(meal_date=d, replace_meal_id=None)
    await state.set_state(AddMealFlow.picking_time)

    now = now_in_tz((await state.get_data()).get("timezone_iana") or "Europe/Moscow")  # fallback; usually profile middleware
    await edit_panel_from_callback(cq, pick_time_text(d), build_time_picker(now))


@router.callback_query(F.data.startswith("calpick:"))
async def calendar_pick_day(cq: CallbackQuery, state: FSMContext, profile):
    data = cq.data
    # using CallbackData parsing:
    picked = None
    try:
        from app.bot.keyboards.calendar import CalendarPickCb, CalendarMode
        cb = CalendarPickCb.unpack(data)
        if cb.mode != CalendarMode.ADD.value:
            await cq.answer()
            return
        picked = date(cb.year, cb.month, cb.day)
    except Exception:
        await cq.answer()
        return

    await state.update_data(meal_date=picked, replace_meal_id=None, timezone_iana=profile.timezone_iana)
    await state.set_state(AddMealFlow.picking_time)

    now = now_in_tz(profile.timezone_iana)
    await edit_panel_from_callback(cq, pick_time_text(picked), build_time_picker(now))


# ========== time picker ==========
@router.callback_query(TimePickCb.filter())
async def time_picked(cq: CallbackQuery, callback_data: TimePickCb, state: FSMContext, session: AsyncSession, user_id):
    st = await state.get_data()
    d: date = st["meal_date"]
    t = time(hour=callback_data.hh, minute=callback_data.mm)

    # создаем meal сразу после выбора времени (черновик)
    repo = MealRepo(session)
    meal = await repo.create_meal(user_id=user_id, meal_date=d, meal_time=t, note=None)

    await state.update_data(meal_time=t, meal_id=str(meal.id))
    await state.set_state(AddMealFlow.typing_items)

    await edit_panel_from_callback(cq, enter_items_text(d, t), reply_markup=None)


@router.callback_query(TimeActionCb.filter(F.action == "custom"))
async def time_custom(cq: CallbackQuery, state: FSMContext):
    await state.set_state(AddMealFlow.typing_custom_time)
    await edit_panel_from_callback(cq, enter_custom_time_text(), reply_markup=None)


@router.message(AddMealFlow.typing_custom_time)
async def time_custom_input(message: Message, state: FSMContext, profile, session: AsyncSession, user_id):
    t0 = parse_time_hhmm(message.text or "")
    if t0 is None:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text="Неверный формат. Введи ЧЧ:ММ, например 08:30",
            reply_markup=None,
        )
        return

    t = snap_to_15(t0)
    st = await state.get_data()
    d: date = st["meal_date"]

    # создаем meal
    repo = MealRepo(session)
    meal = await repo.create_meal(user_id=user_id, meal_date=d, meal_time=t, note=None)

    await state.update_data(meal_time=t, meal_id=str(meal.id))
    await state.set_state(AddMealFlow.typing_items)

    await ensure_panel(
        bot=message.bot,
        chat_id=message.chat.id,
        state=state,
        text=enter_items_text(d, t),
        reply_markup=None,
    )


@router.callback_query(TimeActionCb.filter(F.action == "back"))
async def time_back(cq: CallbackQuery):
    # Возвращаем в быстрый календарь дней
    await cq.answer()
    await cq.message.edit_text("Вернулся назад. Открой день снова через меню.", reply_markup=None)


# ========== items text ==========
@router.message(AddMealFlow.typing_items)
async def items_input(message: Message, state: FSMContext, session: AsyncSession):
    st = await state.get_data()
    meal_id = uuid.UUID(st["meal_id"])
    raw_items = parse_items_csv(message.text or "")
    if not raw_items:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text="Не вижу продуктов. Напиши через запятую, например: макароны, котлеты",
            reply_markup=None,
        )
        return

    repo = MealRepo(session)
    meal = await repo.get_meal(meal_id)
    if meal is None:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text="Ошибка: прием пищи не найден. Попробуй заново.",
            reply_markup=None,
        )
        return

    meal.note = message.text.strip()
    items = await repo.create_items_for_meal(meal_id, raw_items)

    await state.update_data(item_ids=[str(it.id) for it in items], item_index=0)
    await state.set_state(AddMealFlow.mapping_item)

    # показать кандидатов для первого
    await _render_mapping_step(message.chat.id, message.bot, state, session)


async def _render_mapping_step(chat_id: int, bot, state: FSMContext, session: AsyncSession):
    st = await state.get_data()
    idx = int(st["item_index"])
    item_ids: list[str] = st["item_ids"]
    item_id = uuid.UUID(item_ids[idx])

    repo_m = MealRepo(session)
    item = await repo_m.get_item(item_id)
    assert item is not None

    repo_p = ProductRepo(session)
    candidates = await repo_p.search_top_candidates(item.raw_name, limit=10)

    kb = build_product_candidates_kb(item_id, candidates)
    text = map_item_text(item.raw_name, idx + 1, len(item_ids))

    await ensure_panel(
        bot=bot,
        chat_id=chat_id,
        state=state,
        text=text,
        reply_markup=kb,
    )


# ========== mapping ==========
@router.callback_query(ProductPickCb.filter())
async def product_picked(cq: CallbackQuery, callback_data: ProductPickCb, state: FSMContext, session: AsyncSession):
    item_id = uuid.UUID(callback_data.item_id)
    product_id = uuid.UUID(callback_data.product_id)

    repo_m = MealRepo(session)
    await repo_m.set_item_product(item_id, product_id)

    # дальше спрашиваем граммы
    item = await repo_m.get_item(item_id)
    assert item is not None

    await state.update_data(current_item_id=str(item_id))
    await state.set_state(AddMealFlow.typing_grams)

    await edit_panel_from_callback(cq, ask_grams_text(item.raw_name), reply_markup=None)


@router.callback_query(ProductActionCb.filter(F.action == "skip"))
async def product_skip(cq: CallbackQuery, callback_data: ProductActionCb, state: FSMContext, session: AsyncSession):
    item_id = uuid.UUID(callback_data.item_id)

    repo_m = MealRepo(session)
    await repo_m.set_item_product(item_id, None)

    item = await repo_m.get_item(item_id)
    assert item is not None

    await state.update_data(current_item_id=str(item_id))
    await state.set_state(AddMealFlow.typing_grams)

    await edit_panel_from_callback(cq, ask_grams_text(item.raw_name), reply_markup=None)


@router.callback_query(ProductActionCb.filter(F.action == "back"))
async def mapping_back_to_items(cq: CallbackQuery):
    # Упростим: возвращаем в меню (в MVP)
    await cq.answer()
    await cq.message.edit_text("Назад. Открой добавление снова через меню/календарь.", reply_markup=None)


# ========== grams ==========
@router.message(AddMealFlow.typing_grams)
async def grams_input(message: Message, state: FSMContext, session: AsyncSession):
    st = await state.get_data()
    item_id = uuid.UUID(st["current_item_id"])

    try:
        grams = float((message.text or "").replace(",", ".").strip())
        if grams <= 0:
            raise ValueError
    except ValueError:
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text="Введи граммы числом > 0 (например 120).",
            reply_markup=None,
        )
        return

    repo_m = MealRepo(session)
    await repo_m.set_item_grams_and_kcal(item_id, grams)

    # переходим к следующему item или к фото
    st = await state.get_data()
    idx = int(st["item_index"])
    item_ids: list[str] = st["item_ids"]

    idx += 1
    if idx >= len(item_ids):
        # фото-этап
        await state.set_state(AddMealFlow.waiting_photo)
        await state.update_data(item_index=idx, photos_count=0)
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="✅ Готово", callback_data="photo:done")
        b.button(text="⏭ Пропустить фото", callback_data="photo:done")
        b.button(text="⬅️ Назад в меню", callback_data="menu:back")
        b.adjust(1)
        await ensure_panel(
            bot=message.bot,
            chat_id=message.chat.id,
            state=state,
            text="Теперь пришли фото (можно несколько). Когда закончишь — нажми «Готово».",
            reply_markup=b.as_markup(),
        )
        return

    await state.update_data(item_index=idx)
    await state.set_state(AddMealFlow.mapping_item)
    await _render_mapping_step(message.chat.id, message.bot, state, session)


# ========== photos ==========
@router.message(AddMealFlow.waiting_photo, F.photo)
async def photo_received(message: Message, state: FSMContext, session: AsyncSession, user_id, db_user):
    from app.bot.utils.photos import save_telegram_photo_locally
    from app.db.repo_meals import MealRepo

    st = await state.get_data()
    meal_id = uuid.UUID(st["meal_id"])
    meal_date: date = st["meal_date"]

    # берем самое большое фото
    photo = message.photo[-1]
    saved = await save_telegram_photo_locally(
        bot=message.bot,
        tg_user_id=db_user.tg_user_id,
        day=meal_date,
        meal_id=meal_id,
        photo=photo,
    )

    repo = MealRepo(session)
    await repo.add_photo(
        meal_id=meal_id,
        tg_file_id=photo.file_id,
        tg_file_unique_id=photo.file_unique_id,
        local_path=saved.local_path,
        mime_type="image/jpeg",
        width=photo.width,
        height=photo.height,
        file_size_bytes=photo.file_size,
    )

    photos_count = int(st.get("photos_count", 0)) + 1
    await state.update_data(photos_count=photos_count)

    # обновим панель
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="✅ Готово", callback_data="photo:done")
    b.button(text="⬅️ Назад в меню", callback_data="menu:back")
    b.adjust(1)

    await ensure_panel(
        bot=message.bot,
        chat_id=message.chat.id,
        state=state,
        text=f"Фото добавлено: {photos_count}\n\nМожешь отправить еще фото или нажми «Готово».",
        reply_markup=b.as_markup(),
    )


@router.callback_query(AddMealFlow.waiting_photo, F.data == "photo:done")
async def photo_done(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    """
    Финализация.
    Если это редактирование (replace_meal_id) — удаляем старую запись только сейчас.
    """
    st = await state.get_data()
    replace = st.get("replace_meal_id")
    if replace:
        repo = MealRepo(session)
        await repo.delete_meal(uuid.UUID(replace))

    await state.clear()
    await edit_panel_from_callback(cq, "Готово ✅\nЗапись сохранена.", reply_markup=None)
    # вернем меню
    from app.bot.keyboards.menu import main_menu_kb
    from app.bot.utils.text import menu_text
    await cq.message.edit_text(menu_text(), reply_markup=main_menu_kb())
