from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User, UserProfile


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_tg_user_id(self, tg_user_id: int) -> Optional[User]:
        q = select(User).where(User.tg_user_id == tg_user_id)
        return (await self.session.execute(q)).scalars().first()

    async def upsert_user(
        self,
        tg_user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        language_code: Optional[str],
    ) -> User:
        user = await self.get_by_tg_user_id(tg_user_id)
        if user is None:
            user = User(
                tg_user_id=tg_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
            )
            self.session.add(user)
            await self.session.flush()  # получаем user.id
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.language_code = language_code

        # profile (создаем при необходимости)
        if user.profile is None:
            profile = UserProfile(
                user_id=user.id,
                timezone_iana=settings.default_timezone,
                utc_offset_minutes=settings.default_utc_offset_minutes,
            )
            self.session.add(profile)

        return user

    async def get_profile(self, user_id: uuid.UUID) -> UserProfile:
        q = select(UserProfile).where(UserProfile.user_id == user_id)
        profile = (await self.session.execute(q)).scalars().first()
        assert profile is not None, "User profile must exist"
        return profile
