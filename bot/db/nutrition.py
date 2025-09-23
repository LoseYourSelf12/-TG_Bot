from datetime import date
from .core import get_conn

PAGE_SIZE = 8

async def add_food(name:str, kcal_100g:float):
    async with await get_conn() as conn:
        await conn.execute(
            "insert into foods(name, kcal_100g) values(%s,%s) on conflict (name_norm) do update set kcal_100g=excluded.kcal_100g",
            (name.strip(), kcal_100g)
        )

async def list_foods_page(offset:int=0):
    async with await get_conn() as conn:
        cur = await conn.execute("select id, name, kcal_100g from foods order by name_norm limit %s offset %s",
                                 (PAGE_SIZE, offset))
        rows = await cur.fetchall()
        cur = await conn.execute("select count(*) as n from foods")
        total = (await cur.fetchone())["n"]
    return rows, total

async def ensure_meal(tg_id:int, d:date):
    async with await get_conn() as conn:
        cur = await conn.execute("select id from users where tg_id=%s", (tg_id,))
        u = await cur.fetchone()
        cur = await conn.execute("select id from meals where user_id=%s and at_date=%s", (u["id"], d))
        m = await cur.fetchone()
        if m: return m["id"]
        cur = await conn.execute("insert into meals(user_id, at_date) values(%s,%s) returning id", (u["id"], d))
        m = await cur.fetchone()
        return m["id"]

async def add_meal_item(meal_id:int, food_id:int, grams:float, kcal:float):
    async with await get_conn() as conn:
        await conn.execute(
            "insert into meal_items(meal_id, food_id, grams, kcal) values(%s,%s,%s,%s)",
            (meal_id, food_id, grams, kcal)
        )

async def day_items(meal_id:int):
    async with await get_conn() as conn:
        cur = await conn.execute(
            "select mi.id, f.name, mi.grams, mi.kcal from meal_items mi join foods f on f.id=mi.food_id where meal_id=%s order by mi.id desc",
            (meal_id,)
        )
        return await cur.fetchall()

async def day_kcal(meal_id:int) -> float:
    async with await get_conn() as conn:
        cur = await conn.execute("select coalesce(sum(kcal),0) s from meal_items where meal_id=%s", (meal_id,))
        return float((await cur.fetchone())["s"])

async def food_by_id(fid:int):
    async with await get_conn() as conn:
        cur = await conn.execute("select id, name, kcal_100g from foods where id=%s", (fid,))
        return await cur.fetchone()

async def today_kcal(tg_id:int) -> int:
    d = date.today()
    async with await get_conn() as conn:
        cur = await conn.execute("select id from users where tg_id=%s", (tg_id,))
        u = await cur.fetchone()
        if not u: return 0
        cur = await conn.execute("select id from meals where user_id=%s and at_date=%s", (u["id"], d))
        m = await cur.fetchone()
        if not m: return 0
        cur = await conn.execute("select coalesce(sum(kcal),0) s from meal_items where meal_id=%s", (m["id"],))
        return int((await cur.fetchone())["s"])

async def month_days_with_meals(tg_id:int, year:int, month:int) -> set[int]:
    async with await get_conn() as conn:
        # найдём user_id по tg_id, потом все at_date в месяце
        cur = await conn.execute("select id from users where tg_id=%s", (tg_id,))
        u = await cur.fetchone()
        if not u: return set()
        # границы месяца
        from datetime import date, timedelta
        from calendar import monthrange
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        cur = await conn.execute(
            "select at_date from meals where user_id=%s and at_date between %s and %s",
            (u["id"], start, end)
        )
        rows = await cur.fetchall()
        return {r["at_date"].day for r in rows}