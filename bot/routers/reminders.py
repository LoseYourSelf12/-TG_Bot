from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from zoneinfo import ZoneInfo

from db.core import get_conn
from db.users import get_user_by_tg

router = Router()

# ---------- helpers ----------
def time_grid_kb(reminder_id: int, selected: set[tuple[int, int]], page: int = 0):
    """Сетка 24 часа (шаг 1 час) + ручной ввод и назад."""
    kb = InlineKeyboardBuilder()
    for hh in range(0, 24):
        mark = "✅" if (hh, 0) in selected else "➕"
        kb.button(text=f"{mark} {hh:02d}:00",
                  callback_data=f"rem:time:{reminder_id}:{hh}:00:toggle")
        if (hh % 3) == 2:
            kb.adjust(3)
    kb.adjust(3)
    kb.button(text="✍️ Ввести ЧЧ-ММ", callback_data=f"rem:time:{reminder_id}:manual")
    kb.button(text="⬅️ Назад", callback_data=f"rem:back:{reminder_id}")
    kb.adjust(2)
    return kb.as_markup()

def weekdays_kb(reminder_id: int, dows: set[int]):
    """Тумблеры дней недели (1=Пн..7=Вс)."""
    titles = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
    kb = InlineKeyboardBuilder()
    for d in range(1, 8):
        mark = "✅" if d in dows else "⬜"
        kb.button(text=f"{mark} {titles[d]}",
                  callback_data=f"rem:wd:{reminder_id}:{d}:toggle")
    kb.adjust(4, 3)
    kb.button(text="⬅️ Назад", callback_data=f"rem:back:{reminder_id}")
    kb.adjust(1)
    return kb.as_markup()

def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⚖️ Вес (daily)", callback_data="rem:open:weight")
    kb.button(text="🍽 Питание (daily)", callback_data="rem:open:meal")
    kb.button(text="📝 Ежедневные (custom)", callback_data="rem:list:custom_daily")
    kb.button(text="📅 Еженедельные (custom)", callback_data="rem:list:custom_weekly")
    kb.button(text="🎯 Разовые", callback_data="rem:list:oneoff")
    kb.button(text="⬅️ В меню", callback_data="menu:root")
    kb.adjust(1)
    return kb.as_markup()

async def _render(c_or_m, text: str, markup):
    """Если это колбэк — редактируем текущее сообщение, иначе шлём новое."""
    from aiogram.types import CallbackQuery, Message
    if isinstance(c_or_m, CallbackQuery):
        await c_or_m.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await c_or_m.answer()
    else:
        await c_or_m.answer(text, reply_markup=markup, parse_mode="HTML")

# ---------- states ----------
class Rem(StatesGroup):
    manual_time = State()
    custom_text = State()
    oneoff_text = State()
    oneoff_datetime = State()

# ---------- root ----------
@router.message(Command("reminders"))
@router.callback_query(F.data == "rem:root")
async def reminders_root(evt):
    await _render(evt, "Настройка напоминаний.\nВыбери раздел:", main_kb())

# ---------- карточка напоминания ----------
async def render_reminder_card(c_or_m, rid: int):
    async with await get_conn() as conn:
        cur = await conn.execute(
            "select id, kind, enabled from reminders where id=%s", (rid,)
        )
        r = await cur.fetchone()
        if not r:
            return await _render(c_or_m, "Напоминание не найдено", main_kb())

        # текущие времена
        cur = await conn.execute(
            "select hh, mm from reminder_times where reminder_id=%s order by hh, mm",
            (rid,),
        )
        times = [f"{row['hh']:02d}:{row['mm']:02d}" for row in await cur.fetchall()]

        wd_titles = ""
        if r["kind"] == "custom_weekly":
            cur = await conn.execute(
                "select dow from reminder_weekdays where reminder_id=%s order by dow",
                (rid,),
            )
            titles = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
            wd_titles = "Дни: " + (
                ", ".join(titles[d["dow"]] for d in await cur.fetchall()) or "—"
            )

    status = "🟢 Вкл" if r["enabled"] else "🔴 Выкл"
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{status}", callback_data=f"rem:toggle:{rid}")
    if r["kind"] in ("weight", "meal", "custom_daily", "custom_weekly"):
        kb.button(text="⏰ Время", callback_data=f"rem:times:{rid}")
    if r["kind"] == "custom_weekly":
        kb.button(text="📅 Дни недели", callback_data=f"rem:wd:{rid}")
    if r["kind"] in ("custom_daily", "custom_weekly"):
        kb.button(text="✍️ Текст", callback_data=f"rem:text:{rid}")
    if r["kind"] == "oneoff":
        kb.button(text="🗓 Дата/время", callback_data=f"rem:oneoff_dt:{rid}")
        kb.button(text="✍️ Текст", callback_data=f"rem:oneoff_text:{rid}")
    kb.button(text="🗑 Удалить", callback_data=f"rem:del:ask:{rid}")
    kb.button(text="⬅️ Назад", callback_data="rem:root")
    kb.adjust(2, 2, 1, 1)

    times_line = "Время: " + (", ".join(times) if times else "—")
    extra = f"\n{wd_titles}" if wd_titles else ""
    text = f"Напоминание: <b>{r['kind']}</b>\n{times_line}{extra}"
    await _render(c_or_m, text, kb.as_markup())

@router.callback_query(F.data.startswith("rem:openid:"))
async def rem_open_by_id(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    await render_reminder_card(c, rid)

@router.callback_query(F.data.startswith("rem:open:"))
async def rem_open_kind(c: CallbackQuery):
    kind = c.data.split(":")[-1]
    u = await get_user_by_tg(c.from_user.id)
    async with await get_conn() as conn:
        # для weight/meal держим по одному; custom/oneoff — позже через списки
        cur = await conn.execute(
            "select id from reminders where user_id=%s and kind=%s limit 1",
            (u["id"], kind),
        )
        r = await cur.fetchone()
        if not r:
            # ВАЖНО: явно перечисляем колонку enabled, чтобы default=false сработал
            await conn.execute(
                "insert into reminders(user_id, kind, tz, enabled) values(%s,%s,%s,false)",
                (u["id"], kind, u["tz"]),
            )
            cur = await conn.execute(
                "select id from reminders where user_id=%s and kind=%s limit 1",
                (u["id"], kind),
            )
            r = await cur.fetchone()
    await render_reminder_card(c, r["id"])

@router.callback_query(F.data.startswith("rem:back:"))
async def rem_back(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    await render_reminder_card(c, rid)

# ---------- toggle enabled ----------
@router.callback_query(F.data.startswith("rem:toggle:"))
async def rem_toggle(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    async with await get_conn() as conn:
        await conn.execute("update reminders set enabled = not enabled where id=%s", (rid,))
    await render_reminder_card(c, rid)

# ---------- times grid ----------
@router.callback_query(F.data.startswith("rem:times:"))
async def rem_times(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    async with await get_conn() as conn:
        cur = await conn.execute(
            "select hh, mm from reminder_times where reminder_id=%s", (rid,)
        )
        rows = await cur.fetchall()
    selected = {(r["hh"], r["mm"]) for r in rows}
    await _render(c, "Выбери время (шаг 1 час) или ввод ЧЧ-ММ:", time_grid_kb(rid, selected))

@router.callback_query(F.data.startswith("rem:time:") & F.data.endswith(":toggle"))
async def rem_time_toggle(c: CallbackQuery):
    _, _, rid, hh, mm, _ = c.data.split(":")
    rid, hh, mm = int(rid), int(hh), int(mm)
    async with await get_conn() as conn:
        try:
            await conn.execute(
                "insert into reminder_times(reminder_id, hh, mm) values(%s,%s,%s)",
                (rid, hh, mm),
            )
        except Exception:
            await conn.execute(
                "delete from reminder_times where reminder_id=%s and hh=%s and mm=%s",
                (rid, hh, mm),
            )
        cur = await conn.execute(
            "select hh, mm from reminder_times where reminder_id=%s", (rid,)
        )
        rows = await cur.fetchall()
    selected = {(r["hh"], r["mm"]) for r in rows}
    await _render(c, "Выбери время:", time_grid_kb(rid, selected))

@router.callback_query(F.data.startswith("rem:time:") & F.data.endswith(":manual"))
async def rem_time_manual(c: CallbackQuery, state: FSMContext):
    rid = int(c.data.split(":")[2])
    await state.update_data(rem_id=rid)
    await state.set_state(Rem.manual_time)
    await _render(c, "Введи время в формате ЧЧ-ММ (например, 07-30 или 21-00).", None)

@router.message(Rem.manual_time)
async def rem_time_manual_save(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    import re
    if not re.fullmatch(r"\d{2}-\d{2}", txt):
        return await m.answer("Формат ЧЧ-ММ. Пример: 09-00")
    hh, mm = map(int, txt.split("-"))
    data = await state.get_data()
    rid = data["rem_id"]
    async with await get_conn() as conn:
        await conn.execute(
            "insert into reminder_times(reminder_id, hh, mm) values(%s,%s,%s) on conflict do nothing",
            (rid, hh, mm),
        )
        cur = await conn.execute(
            "select hh, mm from reminder_times where reminder_id=%s", (rid,)
        )
        rows = await cur.fetchall()
    selected = {(r["hh"], r["mm"]) for r in rows}
    await state.clear()
    # тут создаём новое сообщение — это ок; «Назад» вернёт в карточку
    await m.answer("Время добавлено.", reply_markup=time_grid_kb(rid, selected))

# ---------- weekdays (weekly) ----------
@router.callback_query(F.data.startswith("rem:wd:") & ~F.data.regexp(r"^\w+:\w+:\d+$"))
async def rem_wd_toggle(c: CallbackQuery):
    _, _, rid, dow, _ = c.data.split(":")
    rid, dow = int(rid), int(dow)
    async with await get_conn() as conn:
        try:
            await conn.execute(
                "insert into reminder_weekdays(reminder_id, dow) values(%s,%s)",
                (rid, dow),
            )
        except Exception:
            await conn.execute(
                "delete from reminder_weekdays where reminder_id=%s and dow=%s",
                (rid, dow),
            )
        cur = await conn.execute(
            "select dow from reminder_weekdays where reminder_id=%s", (rid,)
        )
        rows = await cur.fetchall()
    dows = {r["dow"] for r in rows}
    await _render(c, "Выбери дни недели:", weekdays_kb(rid, dows))

@router.callback_query(F.data.startswith("rem:wd:") & F.data.regexp(r"^\w+:\w+:\d+$"))
async def rem_wd_open(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    async with await get_conn() as conn:
        cur = await conn.execute(
            "select dow from reminder_weekdays where reminder_id=%s", (rid,)
        )
        rows = await cur.fetchall()
    dows = {r["dow"] for r in rows}
    await _render(c, "Выбери дни недели:", weekdays_kb(rid, dows))

# ---------- text for custom/oneoff ----------
@router.callback_query(F.data.startswith("rem:text:"))
async def rem_text_ask(c: CallbackQuery, state: FSMContext):
    rid = int(c.data.split(":")[-1])
    await state.update_data(rem_id=rid)
    await state.set_state(Rem.custom_text)
    await _render(c, "Введи текст напоминания:", None)

@router.message(Rem.custom_text)
async def rem_text_save(m: Message, state: FSMContext):
    data = await state.get_data()
    rid = data["rem_id"]
    async with await get_conn() as conn:
        await conn.execute("update reminders set title=%s where id=%s", (m.text.strip(), rid))
    await state.clear()
    await m.answer("Текст сохранён.", reply_markup=main_kb())

# ---------- oneoff ----------
@router.callback_query(F.data.startswith("rem:oneoff_text:"))
async def rem_oneoff_text(c: CallbackQuery, state: FSMContext):
    rid = int(c.data.split(":")[-1])
    await state.update_data(rem_id=rid)
    await state.set_state(Rem.oneoff_text)
    await _render(c, "Введи текст разового напоминания:", None)

@router.message(Rem.oneoff_text)
async def rem_oneoff_text_save(m: Message, state: FSMContext):
    data = await state.get_data()
    rid = data["rem_id"]
    async with await get_conn() as conn:
        await conn.execute("update reminders set title=%s where id=%s", (m.text.strip(), rid))
    await state.clear()
    await m.answer("Текст сохранён.", reply_markup=main_kb())

@router.callback_query(F.data.startswith("rem:oneoff_dt:"))
async def rem_oneoff_dt(c: CallbackQuery, state: FSMContext):
    rid = int(c.data.split(":")[-1])
    await state.update_data(rem_id=rid)
    await state.set_state(Rem.oneoff_datetime)
    await _render(c, "Введи дату и время: ГГГГ-ММ-ДД ЧЧ-ММ", None)

@router.message(Rem.oneoff_datetime)
async def rem_oneoff_dt_save(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}-\d{2}", txt):
        return await m.answer("Формат: ГГГГ-ММ-ДД ЧЧ-ММ")
    date_s, time_s = txt.split()
    hh, mm = map(int, time_s.split("-"))
    y, mo, d = map(int, date_s.split("-"))
    dt_local = datetime(y, mo, d, hh, mm)  # локальное
    u = await get_user_by_tg(m.from_user.id)
    run_at = dt_local.replace(tzinfo=ZoneInfo(u["tz"])).astimezone(ZoneInfo("UTC"))

    data = await state.get_data()
    rid = data["rem_id"]
    async with await get_conn() as conn:
        await conn.execute(
            "insert into reminder_oneoff(reminder_id, run_at) values(%s,%s) "
            "on conflict (reminder_id) do update set run_at=excluded.run_at, fired=false",
            (rid, run_at),
        )
    await state.clear()
    await m.answer("Разовое напоминание сохранено.", reply_markup=main_kb())

# ---------- snooze / actions from push ----------
@router.callback_query(F.data.startswith("snooze:"))
async def do_snooze(c: CallbackQuery):
    mins = int(c.data.split(":")[1])
    # MVP: только уведомление пользователю (без записи в БД)
    await c.answer(f"Отложено на {mins} мин", show_alert=True)

@router.callback_query(F.data == "act:weight:edit")
async def act_weight_edit(c: CallbackQuery, state: FSMContext):
    # Если у тебя в profile.py есть состояние Edit.weight — лучше использовать именно его:
    # from routers.profile import Edit
    # await state.set_state(Edit.weight)
    await state.set_state(State("Edit:weight"))
    await _render(c, "Введи вес в кг (например, 81.5):", None)

# ---------- списки для custom_* и oneoff ----------
async def list_kb(kind: str, items: list[dict]):
    kb = InlineKeyboardBuilder()
    if not items:
        kb.button(text="➕ Добавить", callback_data=f"rem:add:{kind}")
        kb.button(text="⬅️ Назад", callback_data="rem:root")
        kb.adjust(1, 1)
        return "Список пуст.", kb.as_markup()

    for it in items:
        title = it["title"] or "(без текста)"
        kb.button(text=f"🗂 {title}", callback_data=f"rem:openid:{it['id']}")
        kb.button(text="🗑", callback_data=f"rem:del:ask:{it['id']}")
    kb.adjust(2)
    kb.button(text="➕ Добавить", callback_data=f"rem:add:{kind}")
    kb.button(text="⬅️ Назад", callback_data="rem:root")
    kb.adjust(1, 1)
    return f"Мои {kind}:", kb.as_markup()

@router.callback_query(F.data.startswith("rem:list:"))
async def rem_list(c: CallbackQuery):
    kind = c.data.split(":")[-1]
    u = await get_user_by_tg(c.from_user.id)
    async with await get_conn() as conn:
        cur = await conn.execute(
            "select id, title from reminders where user_id=%s and kind=%s order by id desc",
            (u["id"], kind),
        )
        items = await cur.fetchall()
    text, markup = await list_kb(kind, items)
    await _render(c, text, markup)

@router.callback_query(F.data.startswith("rem:add:"))
async def rem_add(c: CallbackQuery, state: FSMContext):
    kind = c.data.split(":")[-1]
    u = await get_user_by_tg(c.from_user.id)
    async with await get_conn() as conn:
        # ВАЖНО: явно указываем enabled=false
        await conn.execute(
            "insert into reminders(user_id, kind, tz, title, enabled) "
            "values(%s,%s,%s,%s,false)",
            (u["id"], kind, u["tz"], ""),
        )
        cur = await conn.execute(
            "select id from reminders where user_id=%s and kind=%s order by id desc limit 1",
            (u["id"], kind),
        )
        r = await cur.fetchone()
    await render_reminder_card(c, r["id"])

# удаление (с подтверждением)
@router.callback_query(F.data.startswith("rem:del:ask:"))
async def rem_del_ask(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, удалить", callback_data=f"rem:del:yes:{rid}")
    kb.button(text="Отмена", callback_data=f"rem:openid:{rid}")
    kb.adjust(2)
    await _render(c, "Удалить напоминание?", kb.as_markup())

@router.callback_query(F.data.startswith("rem:del:yes:"))
async def rem_del_yes(c: CallbackQuery):
    rid = int(c.data.split(":")[-1])
    async with await get_conn() as conn:
        cur = await conn.execute(
            "select kind, user_id from reminders where id=%s", (rid,)
        )
        r = await cur.fetchone()
        if r:
            kind = r["kind"]
            await conn.execute("delete from reminders where id=%s", (rid,))
            # вернуться к списку этого типа
            cur = await conn.execute(
                "select id, title from reminders where user_id=%s and kind=%s order by id desc",
                (r["user_id"], kind),
            )
            items = await cur.fetchall()
            text, markup = await list_kb(kind, items)
            await _render(c, text, markup)
        else:
            await c.answer("Не найдено", show_alert=True)
