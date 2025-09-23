from .core import get_conn

async def get_user_by_tg(tg_id: int):
    async with await get_conn() as conn:
        cur = await conn.execute("select * from users where tg_id=%s", (tg_id,))
        return await cur.fetchone()

async def upsert_user_profile(tg_id:int, username:str, tz:str, sex:str, birth:str,
                              height_cm:int, weight_kg:float, activity:str,
                              first_name:str|None, last_name:str|None):
    async with await get_conn() as conn:
        await conn.execute(
            """
            insert into users(tg_id, username, tz, sex, birth_date, height_cm, weight_kg, activity_level, tier,
                              first_name, last_name, display_name)
            values(%s,%s,%s,%s,%s,%s,%s,%s,'basic', %s, %s, coalesce(%s, 'пользователь'))
            on conflict (tg_id) do update set
              username=excluded.username, tz=excluded.tz, sex=excluded.sex, birth_date=excluded.birth_date,
              height_cm=excluded.height_cm, weight_kg=excluded.weight_kg, activity_level=excluded.activity_level,
              first_name=excluded.first_name, last_name=excluded.last_name,
              display_name=coalesce(excluded.display_name, users.display_name, 'пользователь')
            """,
            (tg_id, username, tz, sex, birth, height_cm, weight_kg, activity, first_name, last_name, first_name)
        )

async def update_user_field(tg_id:int, field:str, value):
    assert field in {"sex","birth_date","height_cm","weight_kg","activity_level",
                     "first_name","last_name","display_name","role"}
    async with await get_conn() as conn:
        await conn.execute(f"update users set {field}=%s where tg_id=%s", (value, tg_id))

async def ensure_superadmin(tg_id: int):
    async with await get_conn() as conn:
        await conn.execute("update users set role='admin' where tg_id=%s", (tg_id,))

async def has_any_admin() -> bool:
    async with await get_conn() as conn:
        cur = await conn.execute("select 1 from users where role='admin' limit 1")
        return await cur.fetchone() is not None
    
async def delete_user_by_tg(tg_id:int) -> int:
    async with await get_conn() as conn:
        cur = await conn.execute("delete from users where tg_id=%s returning id", (tg_id,))
        rows = await cur.fetchall()
        return len(rows)