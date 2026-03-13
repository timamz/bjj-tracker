from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bjj_bot.models import ArsenalCategory, Base
from bjj_bot.taxonomy import CATEGORY_SEEDS


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, future=True)


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("PRAGMA journal_mode=WAL"))
        await connection.execute(text("PRAGMA synchronous=NORMAL"))

    session_maker = create_session_maker(engine)
    async with session_maker() as session:
        existing_codes = set(await session.scalars(select(ArsenalCategory.code)))
        missing = [
            ArsenalCategory(
                code=seed.code,
                name=seed.name,
                parent_code=seed.parent_code,
                sort_order=seed.sort_order,
            )
            for seed in CATEGORY_SEEDS
            if seed.code not in existing_codes
        ]
        if missing:
            session.add_all(missing)
            await session.commit()

