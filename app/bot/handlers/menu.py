from __future__ import annotations

from datetime import timedelta, date

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.menu import main_menu_kb
from app.bot.keyboards.calendar import build_month_calendar, CalendarMode
from app.bot.utils.text import menu_text, calendar_recent_text
from app.bot.utils.dates import today_in_tz, clamp_add_range
from app.bot.utils.panel import edit_panel_from_callback
from app.db.repo_meals import MealRepo


router = Router()


async def _render_add_quick(
    cq: CallbackQuery,
    profile,
    session: AsyncSession,
    user_id,
):
    # Быстрый выбор: сегодня / вчера / позавчера -> сразу в add-flow
    today = today_in_tz(profile.timezone_iana)
    days = [today, today - timedelta(days=1), today - timedelta(days=2)]

    repo = MealRepo(session)

    # marks для текущего месяца (для ✅📷)
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    start = date(today.year, today.month, 1)
    end = date(today.year, today.month, last_day)
    marks = await repo.month_marks(user_id, start, end)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for d in days:
        label = d.isoformat()
        mark = marks.get(d)
        if mark and mark.meals_count > 0:
            label += " ✅"
        if mark and mark.photos_count > 0:
            label += " 📷"
        b.button(text=label, callback_data=f"day:add:{d.isoformat()}")

    b.button(text="📅 Показать месяц", callback_data=f"menu:open_month_add:{today.year}:{today.month}")
    b.button(text="⬅️ Назад", callback_data="menu:back")
    b.adjust(1)

    await edit_panel_from_callback(
        cq,
        "Добавить прием пищи:\n\nВыбери день (быстрый доступ) или открой календарь месяца.",
        b.as_markup(),
    )


@router.callback_query(F.data == "menu:back")
async def back_to_menu(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await edit_panel_from_callback(cq, menu_text(), main_menu_kb())


@router.callback_query(F.data == "menu:add")
async def menu_add(cq: CallbackQuery, profile, session: AsyncSession, user_id):
    await _render_add_quick(cq, profile, session, user_id)


@router.callback_query(F.data == "menu:calendar_recent")
async def calendar_recent(cq: CallbackQuery, profile, session: AsyncSession, user_id):
    # Это "просмотр дня" (а не добавление): сегодня/вчера/позавчера -> day:view
    today = today_in_tz(profile.timezone_iana)
    days = [today, today - timedelta(days=1), today - timedelta(days=2)]

    repo = MealRepo(session)
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    start = date(today.year, today.month, 1)
    end = date(today.year, today.month, last_day)
    marks = await repo.month_marks(user_id, start, end)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    for d in days:
        label = d.isoformat()
        mark = marks.get(d)
        if mark and mark.meals_count > 0:
            label += " ✅"
        if mark and mark.photos_count > 0:
            label += " 📷"
        b.button(text=label, callback_data=f"day:view:{d.isoformat()}")

    b.button(text="📅 Показать месяц (добавление)", callback_data=f"menu:open_month_add:{today.year}:{today.month}")
    b.button(text="⬅️ Назад", callback_data="menu:back")
    b.adjust(1)

    await edit_panel_from_callback(cq, calendar_recent_text(), b.as_markup())


@router.callback_query(F.data.startswith("menu:open_month_add:"))
async def open_month_add(cq: CallbackQuery, profile, session: AsyncSession, user_id, state: FSMContext):
    _, _, _, y, m = cq.data.split(":")
    year, month = int(y), int(m)

    today = today_in_tz(profile.timezone_iana)
    min_d, max_d = clamp_add_range(today)

    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)

    repo = MealRepo(session)
    marks = await repo.month_marks(user_id, start, end)

    # чтобы "назад" из выбора времени мог вернуться сюда
    await state.update_data(return_to=f"menu:open_month_add:{year}:{month}")

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


@router.callback_query(F.data == "menu:stats")
async def open_stats(cq: CallbackQuery, profile, session: AsyncSession, user_id):
    today = today_in_tz(profile.timezone_iana)
    year, month = today.year, today.month

    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)

    repo = MealRepo(session)
    marks = await repo.month_marks(user_id, start, end)

    kb = build_month_calendar(
        mode=CalendarMode.STATS,
        year=year,
        month=month,
        marks=marks,
        min_date=None,
        max_date=None,
        back_cb="menu:back",
    )
    await edit_panel_from_callback(cq, "Статистика: выбери день в календаре.", kb)


@router.callback_query(F.data == "menu:profile")
async def profile_stub(cq: CallbackQuery):
    await edit_panel_from_callback(
        cq,
        "Профиль (MVP)\n\n"
        "Пока профиль создается автоматически.\n"
        "По умолчанию: Europe/Moscow (UTC+3).\n\n"
        "Позже добавим ввод параметров (вес/рост/цели).",
        main_menu_kb(),
    )
