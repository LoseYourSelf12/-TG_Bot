from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Важно: pool_pre_ping помогает при "битых" соединениях из пула,
# pool_recycle заставляет пересоздавать соединения периодически.
engine = create_async_engine(
    settings.database_dsn,
    pool_pre_ping=True,
    pool_recycle=1800,     # 30 минут
    pool_timeout=30,
    connect_args={
        "timeout": 10,         # timeout подключения (asyncpg)
        "command_timeout": 60, # timeout запросов
    },
)

SessionMaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
