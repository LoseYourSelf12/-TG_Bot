from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

import asyncpg
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.exc import DBAPIError

from app.db.session import SessionMaker, engine


def _is_transient_db_error(e: Exception) -> bool:
    # asyncpg типы
    if isinstance(
        e,
        (
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.ConnectionFailureError,
            asyncpg.exceptions.CannotConnectNowError,
            asyncpg.exceptions.TooManyConnectionsError,
        ),
    ):
        return True

    # Windows сетевые разрывы часто приходят как ConnectionResetError/OSError
    if isinstance(e, (ConnectionResetError, OSError)):
        msg = str(e).lower()
        if "winerror 64" in msg or "connection reset" in msg or "network name" in msg:
            return True

    # SQLAlchemy DBAPIError с orig внутри
    if isinstance(e, DBAPIError) and e.orig is not None:
        return _is_transient_db_error(e.orig)

    return False


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # 1 попытка + 1 ретрай (обычно хватает)
        for attempt in (1, 2):
            session = SessionMaker()
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()

                # если это "плавающее" соединение — пробуем один ретрай
                if attempt == 1 and _is_transient_db_error(e):
                    # На всякий случай сбросим пул, чтобы не брать битые коннекты
                    try:
                        await engine.dispose()
                    except Exception:
                        pass
                    continue

                raise
            finally:
                await session.close()
