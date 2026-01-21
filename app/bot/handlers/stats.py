from __future__ import annotations

from datetime import date, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.calendar import CalendarNavCb, CalendarPickCb, CalendarMode, NoopCb, build_month_calendar
from app.bot.utils.dates import add_month, today_in_tz
from app.bot.utils.panel import edit_panel_from_callback
from app.db.repo_meals import MealRepo
from app.bot.utils.charts import kcal_line_chart


router = Router()


def _week_range(d: date) -> tuple[date, date]:
    # неделя Пн-Вс
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end


def _month_range(d: date) -> tuple[date, date]:
    import calendar
    start = date(d.year, d.month, 1)
    last = calendar.monthrange(d.year, d.month)[1]
    end = date(d.year, d.month, last)
    return start, end


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

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="📋 Открыть день (приемы)", callback_data=f"day:view:{d.isoformat()}")
    b.button(text="📈 Неделя", callback_data=f"stats:week:{d.isoformat()}")
    b.button(text="📊 Месяц", callback_data=f"stats:month:{d.isoformat()}")
    b.button(text="⬅️ Назад к календарю", callback_data="menu:stats")
    b.adjust(1)

    await edit_panel_from_callback(cq, "\n".join(lines), b.as_markup())


@router.callback_query(F.data.startswith("stats:week:"))
async def stats_week(cq: CallbackQuery, session: AsyncSession, user_id):
    d = date.fromisoformat(cq.data.split(":")[2])
    start, end = _week_range(d)

    repo = MealRepo(session)
    days, kcal_vals, total_kcal, total_meals, total_photos = await repo.range_summary(user_id, start, end)

    avg = total_kcal / len(days) if days else 0.0
    max_kcal = max(kcal_vals) if kcal_vals else 0.0
    max_day = days[kcal_vals.index(max_kcal)] if kcal_vals else start

    text = (
        f"📈 Неделя: {start.isoformat()} — {end.isoformat()}\n\n"
        f"Всего ккал: {total_kcal:.0f}\n"
        f"Среднее/день: {avg:.0f}\n"
        f"Приемов: {total_meals}\n"
        f"Фото: {total_photos}\n"
        f"Самый калорийный день: {max_day.isoformat()} ({max_kcal:.0f} ккал)"
    )

    await cq.answer()
    await cq.message.edit_text(text, reply_markup=None)

    chart = kcal_line_chart(days, kcal_vals, title=f"Ккал по дням (неделя {start.isoformat()}—{end.isoformat()})")
    await cq.bot.send_photo(chat_id=cq.message.chat.id, photo=chart)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="📅 Вернуться к дню", callback_data="menu:stats")
    b.button(text="⬅️ В меню", callback_data="menu:back")
    b.adjust(1)
    await cq.bot.send_message(chat_id=cq.message.chat.id, text="Дальше:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("stats:month:"))
async def stats_month(cq: CallbackQuery, session: AsyncSession, user_id):
    d = date.fromisoformat(cq.data.split(":")[2])
    start, end = _month_range(d)

    repo = MealRepo(session)
    days, kcal_vals, total_kcal, total_meals, total_photos = await repo.range_summary(user_id, start, end)

    avg = total_kcal / len(days) if days else 0.0
    max_kcal = max(kcal_vals) if kcal_vals else 0.0
    max_day = days[kcal_vals.index(max_kcal)] if kcal_vals else start

    # days_with_records
    days_with_records = sum(1 for v in kcal_vals if v > 0)

    text = (
        f"📊 Месяц: {start.strftime('%Y-%m')}\n\n"
        f"Всего ккал: {total_kcal:.0f}\n"
        f"Среднее/день: {avg:.0f}\n"
        f"Дней с записями: {days_with_records}/{len(days)}\n"
        f"Приемов: {total_meals}\n"
        f"Фото: {total_photos}\n"
        f"Самый калорийный день: {max_day.isoformat()} ({max_kcal:.0f} ккал)"
    )

    await cq.answer()
    await cq.message.edit_text(text, reply_markup=None)

    chart = kcal_line_chart(days, kcal_vals, title=f"Ккал по дням (месяц {start.strftime('%Y-%m')})")
    await cq.bot.send_photo(chat_id=cq.message.chat.id, photo=chart)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="📅 Вернуться к календарю", callback_data="menu:stats")
    b.button(text="⬅️ В меню", callback_data="menu:back")
    b.adjust(1)
    await cq.bot.send_message(chat_id=cq.message.chat.id, text="Дальше:", reply_markup=b.as_markup())
