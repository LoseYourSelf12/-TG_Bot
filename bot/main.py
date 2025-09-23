import asyncio, os, logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder

from routers.registration import router as reg_router
from routers.profile import router as profile_router
from routers.nutrition import router as nutrition_router
from routers.reminders import router as reminders_router
from db.users import ensure_superadmin, has_any_admin

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("bot")

API_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    if not API_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в окружении")

    storage = RedisStorage.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        key_builder=DefaultKeyBuilder(with_bot_id=True),
    )
    dp = Dispatcher(storage=storage)
    dp.include_router(reg_router)
    dp.include_router(profile_router)
    dp.include_router(nutrition_router)
    dp.include_router(reminders_router)

    bot = Bot(API_TOKEN)
    sid = os.getenv("SUPERADMIN_TG_ID")
    if sid and sid.isdigit():
        await ensure_superadmin(int(sid))

    log.info("Starting polling…")
    await dp.start_polling(bot, allowed_updates=["message","callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
