from __future__ import annotations

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    database_dsn: str

    photo_dir: str = "./data/photos"
    default_timezone: str = "Europe/Moscow"
    default_utc_offset_minutes: int = 180

    # пример: ADMIN_IDS=12345,67890
    admin_ids_raw: str = "6175512444"

    @property
    def admin_ids(self) -> List[int]:
        raw = (self.admin_ids_raw or "").strip()
        if not raw:
            return []
        return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


settings = Settings()
