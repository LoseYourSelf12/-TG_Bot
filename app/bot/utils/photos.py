from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import aiofiles
from aiogram import Bot
from aiogram.types import PhotoSize

from app.config import settings


@dataclass(frozen=True)
class SavedPhoto:
    local_path: str


async def save_telegram_photo_locally(
    bot: Bot,
    tg_user_id: int,
    day: date,
    meal_id: uuid.UUID,
    photo: PhotoSize,
) -> SavedPhoto:
    """
    Скачиваем фото в PHOTO_DIR/<tg_user_id>/<YYYY-MM-DD>/<meal_id>/<file_unique_id>.jpg
    """
    base = Path(settings.photo_dir) / str(tg_user_id) / day.isoformat() / str(meal_id)
    base.mkdir(parents=True, exist_ok=True)

    # file_unique_id стабильнее, но на всякий случай fallback
    name = (photo.file_unique_id or photo.file_id).replace("/", "_")
    filepath = base / f"{name}.jpg"

    f = await bot.get_file(photo.file_id)
    # bot.download_file — в aiogram можно получать bytes и писать самим
    file_bytes = await bot.download_file(f.file_path)

    async with aiofiles.open(filepath, "wb") as out:
        await out.write(file_bytes.read())

    return SavedPhoto(local_path=str(filepath))
