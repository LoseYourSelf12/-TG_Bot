from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo_users import UserRepo


class UserContextMiddleware(BaseMiddleware):
    """
    Гарантирует, что пользователь и профиль существуют.
    Прокидывает:
      data["db_user"]  -> User
      data["user_id"]  -> UUID
      data["profile"]  -> UserProfile
    """

    async def __call__(self, handler, event: TelegramObject, data: Dict[str, Any]) -> Any:
        session: AsyncSession = data["session"]

        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user is not None:
            repo = UserRepo(session)
            user = await repo.upsert_user(
                tg_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code,
            )
            profile = await repo.get_profile(user.id)
            data["db_user"] = user
            data["user_id"] = user.id
            data["profile"] = profile

        return await handler(event, data)
