from __future__ import annotations

import uuid
from datetime import date, time

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import AddMealFlow
from app.bot.keyboards.time_picker import build_time_picker, TimePickCb, TimeActionCb
from app.bot.keyboards.products import build_product_candidates_kb, ProductPickCb, ProductActionCb, ProductPageCb
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

from app.bot.keyboards.meals import build_day_meals_kb
from app.bot.keyboards.menu import main_menu_kb
from app.bot.utils.text import menu_text
from app.bot.keyboards.calendar import build_month_calendar, CalendarMode
from app.bot.utils.dates import today_in_tz, clamp_add_range, add_month
from app.bot.utils.ids import short_to_uuid


router = Router()

from aiogram.filters import StateFilter


def _grams_kb() -> "object":
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад к выбору продукта", callback_data="grams:back")
    b.button(text="⬅️ В меню", callback_data="menu:back")
    b.adjust(1)
    return b.as_markup()


async def _render_return_screen(
    cq: CallbackQuery,
    *,
    state: FSMContext,
    profile,
    session: AsyncSession,
    user_id,
):
    """
    Возврат с шага выбора времени "Назад".
    """
    st = await state.get_data()
    return_to = st.get("return_to")  # например: day:view:YYYY-MM-DD | menu:add | menu:open_month_add:Y:M
    await state.clear()

    if isinstance(return_to, str) and return_to.startswith("day:view:"):
        day_str = return_to.split(":", 2)[2]
        d = date.fromisoformat(day_str)
        repo = MealRepo(session)
        meals = await repo.list_meals_by_day(user_id, d)
        await edit_panel_from_callback(cq, f"День: {d.isoformat()}\n\nВыбери прием пищи или добавь новый.", build_day_meals_kb(d, meals, back_cb="menu:calendar_recent"))
        return

    if isinstance(return_to, str) and return_to.startswith("menu:open_month_add:"):
        _, _, y, m = return_to.split(":")
        year, month = int(y), int(m)

        today = today_in_tz(profile.timezone_iana)
        min_d, max_d = clamp_add_range(today)

        import calendar
        last_day = calendar.monthrange(year, month)[1]
        start = date(year, month, 1)
        end = date(year, month, last_day)
        repo = MealRepo(session)
        marks = await repo.month_marks(user_id, start, end)

        kb = build_month_calendar(
            mode=CalendarMode.ADD,
            year=year,
            month=month,
            marks=marks,
            min_date=min_d,
            max_date=max_d,
            back_cb="menu:add",
        )
        await edit_panel_from_callback(cq, "Календарь (добавление):", kb)
        return

    if return_to == "menu:add":
        # повторим экран добавления (быстрый)
        from app.bot.handlers.menu import _render_add_quick
        await _render_add_quick(cq, profile, session, user_id)
        return

    await edit_panel_from_callback(cq, menu_text(), main_menu_kb())


# ========== entry points ==========
@router.callback_query(F.data.startswith("day:add:"))
async def day_add_meal(cq: CallbackQuery, state: FSMContext, profile):
    _, _, day_str = cq.data.split(":")
    d = date.fromisoformat(day_str)

    await state.update_data(
        meal_date=d,
        replace_meal_id=None,
        return_to=f"day:view:{d.isoformat()}",
    )
    await state.set_state(AddMealFlow.picking_time)

    now = now_in_tz(profile.timezone_iana)
    await edit_panel_from_callback(cq, pick_time_text(d), build_time_picker(now))


async def _cleanup_draft(session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    meal_id = data.get("meal_id")
    if meal_id:
        repo = MealRepo(session)
        await repo.delete_meal(uuid.UUID(meal_id))


@router.callback_query(StateFilter(AddMealFlow), F.data == "menu:back")
async def flow_cancel_to_menu(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    # если начали flow и уже создали meal (после выбора времени), удаляем черновик
    await _cleanup_draft(session, state)
    await state.clear()
    from app.bot.utils.text import menu_text
    from app.bot.keyboards.menu import main_menu_kb
    from app.config import settings
    is_admin = cq.from_user.id in settings.admin_ids
    await edit_panel_from_callback(cq, menu_text(), main_menu_kb(is_admin=is_admin))


# ========== time picker ==========
@router.callback_query(AddMealFlow.picking_time, TimePickCb.filter())
async def time_picked(cq: CallbackQuery, callback_data: TimePickCb, state: FSMContext, session: AsyncSession, user_id):
    st = await state.get_data()
    d: date = st["meal_date"]
    t = time(hour=callback_data.hh, minute=callback_data.mm)

    repo = MealRepo(session)
    meal = await repo.create_meal(user_id=user_id, meal_date=d, meal_time=t, note=None)

    await state.update_data(meal_time=t, meal_id=str(meal.id))
    await state.set_state(AddMealFlow.typing_items)

    await edit_panel_from_callback(cq, enter_items_text(d, t), reply_markup=None)


@router.callback_query(AddMealFlow.picking_time, TimeActionCb.filter(F.action == "custom"))
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


@router.callback_query(AddMealFlow.picking_time, TimeActionCb.filter(F.action == "back"))
async def time_back(cq: CallbackQuery, state: FSMContext, profile, session: AsyncSession, user_id):
    await _render_return_screen(cq, state=state, profile=profile, session=session, user_id=user_id)


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

    # Авто-маппинг: точное совпадение по name или synonym
    repo_p = ProductRepo(session)
    for it in items:
        exact = await repo_p.find_exact_product(it.raw_name)
        if exact:
            await repo.set_item_product(it.id, exact.id)

    await state.update_data(item_ids=[str(it.id) for it in items], item_index=0)
    await state.set_state(AddMealFlow.mapping_item)
    await _render_mapping_step(message.chat.id, message.bot, state, session)


async def _render_mapping_step(chat_id: int, bot, state: FSMContext, session: AsyncSession, page: int = 1):
    st = await state.get_data()
    idx = int(st["item_index"])
    item_ids: list[str] = st["item_ids"]
    item_id = uuid.UUID(item_ids[idx])

    repo_m = MealRepo(session)
    item = await repo_m.get_item(item_id)
    assert item is not None

    repo_p = ProductRepo(session)

    # Если ещё не выбран продукт — пробуем exact match и ставим его как "выбран по умолчанию",
    # но всё равно показываем список (как ты хотел).
    if item.product_ref_id is None:
        exact = await repo_p.find_exact_product(item.raw_name)
        if exact:
            await repo_m.set_item_product(item_id, exact.id)

    # Подтягиваем item заново (чтобы увидеть выбранный product_ref_id)
    item = await repo_m.get_item(item_id)
    assert item is not None

    page_size = 10
    total_candidates = 0
    candidates = []
    candidates, total_candidates = await repo_p.search_ranked_candidates(
        item.raw_name,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    total_pages = max(1, (total_candidates + page_size - 1) // page_size)
    page = max(1, min(total_pages, page))

    kb = build_product_candidates_kb(
        item_id=item_id,
        candidates=candidates,
        selected_product_id=item.product_ref_id,
        page=page,
        total_pages=total_pages,
    )

    # Текст: каноническое имя, если выбрано
    chosen_line = ""
    if item.product_ref_id:
        prod = await repo_p.get_product(item.product_ref_id)
        if prod:
            if str(prod.name).casefold() == item.raw_name.casefold():
                chosen_line = f"Текущее: ✅ {prod.name}\n\n"
            else:
                chosen_line = f"Текущее: ✅ {prod.name} (ввели: {item.raw_name})\n\n"

    text = (
        f"{chosen_line}"
        f"Продукт {idx + 1}/{len(item_ids)}\n\n"
        f"Выбери продукт из справочника:\n"
        f"🎯 точное совпадение → 🔎 похожие по названию → 🔁 похожие синонимы"
    )

    await ensure_panel(
        bot=bot,
        chat_id=chat_id,
        state=state,
        text=text,
        reply_markup=kb,
    )


# ========== mapping ==========
@router.callback_query(AddMealFlow.mapping_item, ProductPickCb.filter())
async def product_picked(cq: CallbackQuery, callback_data: ProductPickCb, state: FSMContext, session: AsyncSession):
    from app.bot.utils.ids import short_to_uuid

    item_id = short_to_uuid(callback_data.item)
    product_id = short_to_uuid(callback_data.prod)

    repo_m = MealRepo(session)
    await repo_m.set_item_product(item_id, product_id)

    item = await repo_m.get_item(item_id)
    if item is None:
        await cq.answer("Ошибка: позиция не найдена", show_alert=True)
        return

    # для подтверждения покажем, что привязали
    repo_p = ProductRepo(session)
    prod = await repo_p.get_product(product_id)
    prod_name = str(prod.name) if prod else "неизвестный продукт"

    await state.update_data(current_item_id=str(item_id))
    await state.set_state(AddMealFlow.typing_grams)

    await edit_panel_from_callback(
        cq,
        f"Выбрано: ✅ {prod_name}\n\nВведи граммы:",
        reply_markup=_grams_kb(),
    )


@router.callback_query(AddMealFlow.mapping_item, ProductActionCb.filter(F.action == "skip"))
async def product_skip(cq: CallbackQuery, callback_data: ProductActionCb, state: FSMContext, session: AsyncSession):
    item_id = short_to_uuid(callback_data.item)

    repo_m = MealRepo(session)
    await repo_m.set_item_product(item_id, None)

    item = await repo_m.get_item(item_id)
    assert item is not None

    await state.update_data(current_item_id=str(item_id))
    await state.set_state(AddMealFlow.typing_grams)

    await edit_panel_from_callback(cq, ask_grams_text(item.raw_name), reply_markup=_grams_kb())


@router.callback_query(AddMealFlow.typing_grams, F.data == "grams:back")
async def grams_back_to_mapping(cq: CallbackQuery, state: FSMContext, session: AsyncSession):
    st = await state.get_data()
    cur = st.get("current_item_id")
    item_ids: list[str] = st.get("item_ids", [])
    if not cur or cur not in item_ids:
        await cq.answer()
        return

    await state.update_data(item_index=item_ids.index(cur))
    await state.set_state(AddMealFlow.mapping_item)
    await _render_mapping_step(cq.message.chat.id, cq.bot, state, session)
    await cq.answer()


@router.callback_query(AddMealFlow.mapping_item, ProductActionCb.filter(F.action == "back"))
async def mapping_back_to_items(cq: CallbackQuery, state: FSMContext, profile, session: AsyncSession, user_id):
    # MVP: возвращаемся на экран "Назад" откуда пришли (вне item mapping углубляться не будем)
    await _render_return_screen(cq, state=state, profile=profile, session=session, user_id=user_id)


@router.callback_query(AddMealFlow.mapping_item, ProductPageCb.filter())
async def product_page(cq: CallbackQuery, callback_data: ProductPageCb, state: FSMContext, session: AsyncSession):
    item_id = short_to_uuid(callback_data.item)

    # синхронизируем item_index по item_id (на случай, если пользователь листает позже)
    st = await state.get_data()
    item_ids: list[str] = st.get("item_ids", [])
    if str(item_id) in item_ids:
        await state.update_data(item_index=item_ids.index(str(item_id)))

    await _render_mapping_step(cq.message.chat.id, cq.bot, state, session, page=callback_data.page)
    await cq.answer()

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
            reply_markup=_grams_kb(),
        )
        return

    repo_m = MealRepo(session)
    await repo_m.set_item_grams_and_kcal(item_id, grams)

    st = await state.get_data()
    idx = int(st["item_index"])
    item_ids: list[str] = st["item_ids"]

    idx += 1
    if idx >= len(item_ids):
        await state.set_state(AddMealFlow.waiting_photo)
        await state.update_data(item_index=idx, photos_count=0)

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="✅ Готово", callback_data="photo:done")
        b.button(text="⏭ Пропустить фото", callback_data="photo:done")
        b.button(text="⬅️ В меню", callback_data="menu:back")
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
async def photo_received(message: Message, state: FSMContext, session: AsyncSession, db_user):
    from app.bot.utils.photos import save_telegram_photo_locally

    st = await state.get_data()
    meal_id = uuid.UUID(st["meal_id"])
    meal_date: date = st["meal_date"]

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

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="✅ Готово", callback_data="photo:done")
    b.button(text="⬅️ В меню", callback_data="menu:back")
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
    st = await state.get_data()
    replace = st.get("replace_meal_id")
    if replace:
        repo = MealRepo(session)
        await repo.delete_meal(uuid.UUID(replace))

    await state.clear()
    await edit_panel_from_callback(cq, "Готово ✅\nЗапись сохранена.", reply_markup=main_menu_kb())
