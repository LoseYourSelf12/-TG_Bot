from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.bot.handlers import build_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.user_context import UserContextMiddleware


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    db_mw = DbSessionMiddleware()
    user_mw = UserContextMiddleware()

    dp.message.middleware(db_mw)
    dp.callback_query.middleware(db_mw)

    dp.message.middleware(user_mw)
    dp.callback_query.middleware(user_mw)

    dp.include_router(build_router())

    os.makedirs(settings.photo_dir, exist_ok=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
