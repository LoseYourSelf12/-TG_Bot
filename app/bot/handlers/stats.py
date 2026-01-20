from __future__ import annotations

from datetime import date
import uuid

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.calendar import CalendarNavCb, CalendarPickCb, CalendarMode, NoopCb, build_month_calendar
from app.bot.utils.dates import add_month, today_in_tz
from app.bot.utils.panel import edit_panel_from_callback
from app.db.repo_meals import MealRepo


router = Router()


@router.callback_query(NoopCb.filter())
async def noop(cq: CallbackQuery):
    cb = NoopCb.unpack(cq.data)
    if cb.why == "out_of_range":
        await cq.answer("Можно выбрать только даты за последние 30 дней.", show_alert=True)
        return
    await cq.answer()


@router.callback_query(CalendarNavCb.filter())
async def calendar_nav(cq: CallbackQuery, session: AsyncSession, user_id, profile):
    cb = CalendarNavCb.unpack(cq.data)
    year, month = cb.year, cb.month
    delta = -1 if cb.direction == "prev" else 1
    ny, nm = add_month(year, month, delta)

    import calendar
    last = calendar.monthrange(ny, nm)[1]
    start = date(ny, nm, 1)
    end = date(ny, nm, last)

    repo = MealRepo(session)
    marks = await repo.month_marks(user_id, start, end)

    mode = CalendarMode(cb.mode)
    # ограничения только в режиме добавления, но этот обработчик общий
    min_d = max_d = None
    if mode == CalendarMode.ADD:
        t = today_in_tz(profile.timezone_iana)
        from app.bot.utils.dates import clamp_add_range
        min_d, max_d = clamp_add_range(t)

    kb = build_month_calendar(
        mode=mode,
        year=ny,
        month=nm,
        marks=marks,
        min_date=min_d,
        max_date=max_d,
        back_cb="menu:back" if mode == CalendarMode.STATS else "menu:calendar_recent",
    )
    await edit_panel_from_callback(cq, "Выбери день:", kb)


@router.callback_query(F.data.startswith("calpick:"))
async def stats_pick_day(cq: CallbackQuery, session: AsyncSession, user_id):
    """
    Для режима статистики: клик по дню -> показать дневную статистику.
    В add_meal.py также есть обработчик calpick, он игнорирует не-ADD.
    """
    try:
        cb = CalendarPickCb.unpack(cq.data)
    except Exception:
        await cq.answer()
        return

    if cb.mode != CalendarMode.STATS.value:
        await cq.answer()
        return

    d = date(cb.year, cb.month, cb.day)
    repo = MealRepo(session)
    meals = await repo.list_meals_by_day(user_id, d)

    # Интервалы между ближайшими приемами (между соседними)
    times = [m.meal_time for m in meals]
    intervals = []
    for i in range(1, len(times)):
        a = times[i - 1]
        b = times[i]
        mins = (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)
        intervals.append(mins)

    total_kcal = 0.0
    photos_total = 0
    for m in meals:
        items = await repo.list_items(m.id)
        total_kcal += sum(float(it.kcal_total or 0.0) for it in items)
        photos_total += len(await repo.list_photos(m.id))

    lines = [
        f"Статистика за {d.isoformat()}",
        "",
        f"Приемов пищи: {len(meals)}",
        f"Фото: {photos_total}",
        f"Калорийность (из справочника): {total_kcal:.0f} ккал",
    ]
    if intervals:
        lines.append("")
        lines.append("Интервалы между приемами (мин): " + ", ".join(str(x) for x in intervals))

    # Покажем кнопки: открыть день (список приемов) или назад к календарю
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="📋 Открыть день (приемы)", callback_data=f"day:view:{d.isoformat()}")
    b.button(text="⬅️ Назад к календарю", callback_data="menu:stats")
    b.adjust(1)

    await edit_panel_from_callback(cq, "\n".join(lines), b.as_markup())
