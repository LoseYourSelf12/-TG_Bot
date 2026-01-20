from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    database_dsn: str

    photo_dir: str = "./data/photos"

    default_timezone: str = "Europe/Moscow"
    default_utc_offset_minutes: int = 180


settings = Settings()
