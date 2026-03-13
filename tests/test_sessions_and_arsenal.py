from __future__ import annotations

from datetime import date

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bjj_bot.db import init_db
from bjj_bot.services import arsenal as arsenal_service
from bjj_bot.services import promotions as promotion_service
from bjj_bot.services import sessions as session_service
from bjj_bot.services import users as user_service


@pytest.fixture()
async def session_maker(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    await init_db(engine, db_path)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def make_tg_user(user_id: int) -> TelegramUser:
    return TelegramUser(id=user_id, is_bot=False, first_name="Tim", username=f"user{user_id}")


@pytest.mark.asyncio
async def test_create_move_and_log_session(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(10))
        move = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Scissor Sweep",
            category_code="sweeps_closed",
            note="Angle first",
            tags=["gi", "fundamental"],
        )
        training_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 13),
            move_ids=[move.id],
        )
        count = await session_service.count_practiced_moves(session, training_session.id)
        progress = await user_service.get_progress(session, user.id)

    assert count == 1
    assert progress.total_sessions == 1


@pytest.mark.asyncio
async def test_promotion_uses_current_session_count(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(20))
        await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 10),
            move_ids=[],
        )
        promotion = await promotion_service.apply_promotion(
            session,
            user_id=user.id,
            promotion_date=date(2026, 3, 11),
            kind="stripe",
        )

    assert promotion.session_number == 1


@pytest.mark.asyncio
async def test_taxonomy_seeded(session_maker) -> None:
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, None)
    assert any(node.category.code == "standing" for node in categories)
    assert any(node.category.code == "guard" for node in categories)
