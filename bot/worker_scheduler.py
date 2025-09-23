import os, asyncio, json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import psycopg
from psycopg.rows import dict_row
from aiokafka import AIOKafkaProducer
from calendar import day_name

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
PG_DSN = os.getenv("PG_DSN_NATIVE", "dbname=app user=app password=app host=postgres port=5432")

async def pg():
    return await psycopg.AsyncConnection.connect(PG_DSN, row_factory=dict_row)

async def due_windows():
    now = datetime.now(timezone.utc)
    # окно на ближайшую минуту
    return now, now + timedelta(seconds=60)

async def fetch_candidates(conn, start_utc, end_utc):
    # Простая стратегия: забираем все reminders enabled и проверяем в питоне (достаточно быстро для MVP)
    cur = await conn.execute("select r.*, u.tg_id, u.tz as user_tz from reminders r join users u on u.id=r.user_id where r.enabled=true")
    return await cur.fetchall()

def local_times_for_today(r, now_utc):
    tz = ZoneInfo(r["tz"])
    now_local = now_utc.astimezone(tz)
    weekday = now_local.isoweekday()  # 1..7
    times = []

    if r["kind"] in ("weight","meal","custom_daily","custom_weekly"):
        # times:
        # load times
        # weekly: check weekday
        # we'll fetch later per reminder; here returning None
        pass

    return times

async def times_for_reminder(conn, r, window_start_utc, window_end_utc):
    tz = ZoneInfo(r["tz"])
    now_local = datetime.now(timezone.utc).astimezone(tz)
    weekday = now_local.isoweekday()

    # snooze check
    cur = await conn.execute("select 1 from reminder_snoozes where reminder_id=%s and until_at > now()", (r["id"],))
    if await cur.fetchone():
        return []

    out = []

    if r["kind"] in ("weight","meal","custom_daily"):
        cur = await conn.execute("select hh, mm from reminder_times where reminder_id=%s", (r["id"],))
        for row in await cur.fetchall():
            lt = now_local.replace(hour=row["hh"], minute=row["mm"], second=0, microsecond=0)
            ut = lt.astimezone(timezone.utc)
            if window_start_utc <= ut < window_end_utc:
                out.append((ut, f"{row['hh']:02d}:{row['mm']:02d}"))
    elif r["kind"] == "custom_weekly":
        curd = await conn.execute("select dow from reminder_weekdays where reminder_id=%s", (r["id"],))
        dows = {x["dow"] for x in await curd.fetchall()}
        if weekday in dows:
            cur = await conn.execute("select hh, mm from reminder_times where reminder_id=%s", (r["id"],))
            for row in await cur.fetchall():
                lt = now_local.replace(hour=row["hh"], minute=row["mm"], second=0, microsecond=0)
                ut = lt.astimezone(timezone.utc)
                if window_start_utc <= ut < window_end_utc:
                    out.append((ut, f"{row['hh']:02d}:{row['mm']:02d}"))
    elif r["kind"] == "oneoff":
        cur = await conn.execute("select run_at, fired from reminder_oneoff where reminder_id=%s", (r["id"],))
        row = await cur.fetchone()
        if row and not row["fired"]:
            run_at = row["run_at"]
            if window_start_utc <= run_at < window_end_utc:
                out.append((run_at, run_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")))
    return out

def build_text(r):
    if r["kind"] == "weight":
        return "🔔 Напоминание: встань на весы."
    if r["kind"] == "meal":
        return "🍽 Пора поесть. Заполни приём пищи."
    # custom
    return r.get("title") or "Напоминание"

def build_buttons(r):
    # инлайн-кнопки для действий
    if r["kind"] == "weight":
        return [["✏️ Обновить вес", "act:weight:edit"], ["⏰ Отложить 15", "snooze:15"], ["⏰ 30", "snooze:30"], ["⏰ 60", "snooze:60"]]
    if r["kind"] in ("meal","custom_daily","custom_weekly","oneoff"):
        return [["➕ Записать питание", "act:meal:add"], ["⏰ 15", "snooze:15"], ["⏰ 30", "snooze:30"], ["⏰ 60", "snooze:60"]]
    return []

async def main():
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await producer.start()
    try:
        while True:
            win_start, win_end = await due_windows()
            async with await pg() as conn:
                reminders = await fetch_candidates(conn, win_start, win_end)
                for r in reminders:
                    times = await times_for_reminder(conn, r, win_start, win_end)
                    for ut, label in times:
                        # idem key
                        dedup_key = f"{ut.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M')}"
                        # пытаемся записать лог (если уже есть — пропускаем)
                        try:
                            await conn.execute(
                                "insert into reminder_logs(reminder_id, fired_at, dedup_key) values(%s, now(), %s)",
                                (r["id"], dedup_key)
                            )
                        except Exception:
                            continue
                        payload = {
                            "reminder_id": r["id"],
                            "chat_id": r["tg_id"],
                            "text": build_text(r),
                            "buttons": build_buttons(r),
                            "silent": True,
                            "dedup_key": dedup_key,
                        }
                        await producer.send_and_wait("reminder.fire", json.dumps(payload, ensure_ascii=False).encode(), key=str(r["user_id"]).encode())
                # mark oneoff fired
                await conn.execute("""
                  update reminder_oneoff o
                  set fired = true
                  from reminders r
                  where o.reminder_id=r.id and r.enabled=true and o.run_at >= %s and o.run_at < %s
                """, (win_start, win_end))
            await asyncio.sleep(30)
    finally:
        await producer.stop()

if __name__ == "__main__":
    asyncio.run(main())
