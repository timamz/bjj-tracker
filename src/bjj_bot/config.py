from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    db_path: Path = Field(default=Path("/data/bjj_bot.sqlite3"), alias="DB_PATH")
    timezone: str = Field(default="UTC", alias="TIMEZONE")
    rank_stickers_raw: str = Field(default="{}", alias="RANK_STICKERS")

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def rank_stickers(self) -> dict[str, str]:
        try:
            parsed = json.loads(self.rank_stickers_raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(key): str(value) for key, value in parsed.items()}

