from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bjj_bot.config import Settings
from bjj_bot.db import create_engine, create_session_maker, init_db
from bjj_bot.handlers.admin import router as admin_router
from bjj_bot.handlers.menu import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = create_engine(settings.database_url)
    await init_db(engine, settings.db_path)
    session_maker = create_session_maker(engine)

    session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else None
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(admin_router)
    dispatcher.include_router(router)
    dispatcher["session_maker"] = session_maker
    dispatcher["settings"] = settings

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

