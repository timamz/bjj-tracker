from __future__ import annotations

from datetime import date

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bjj_bot.db import init_db
from bjj_bot.services import arsenal as arsenal_service
from bjj_bot.services import history as history_service
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
async def test_log_session_with_multiple_moves(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(11))
        move_one = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Knee Cut",
            category_code="transitions_passes",
            note="Crossface first",
            tags=["gi"],
        )
        move_two = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Toreando",
            category_code="transitions_passes",
            note="Pin the hips",
            tags=["no-gi"],
        )
        training_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 14),
            move_ids=[move_one.id, move_two.id],
        )
        count = await session_service.count_practiced_moves(session, training_session.id)
        progress = await user_service.get_progress(session, user.id)

    assert count == 2
    assert progress.total_sessions == 1


@pytest.mark.asyncio
async def test_update_move_fields(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(12))
        move = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Old Name",
            category_code="guard_closed",
            note="Old note",
            tags=["gi"],
        )
        updated = await arsenal_service.update_move(
            session,
            user_id=user.id,
            move_id=move.id,
            name="New Name",
            category_code="transitions_passes",
            note="New note",
            tags=["no-gi", "pressure"],
        )

    assert updated is not None
    assert updated.name == "New Name"
    assert updated.category_code == "transitions_passes"
    assert updated.note == "New note"
    assert sorted(tag.value for tag in updated.tags) == ["no-gi", "pressure"]


@pytest.mark.asyncio
async def test_delete_move_removes_session_links(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(13))
        move = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Single Leg X Sweep",
            category_code="sweeps_leg_entanglement",
            note="Lift the heel",
            tags=["gi"],
        )
        training_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 15),
            move_ids=[move.id],
        )
        deleted = await arsenal_service.delete_move(session, user_id=user.id, move_id=move.id)
        count = await session_service.count_practiced_moves(session, training_session.id)
        still_exists = await arsenal_service.get_move(session, user.id, move.id)

    assert deleted is True
    assert count == 0
    assert still_exists is None


@pytest.mark.asyncio
async def test_update_session_changes_date_and_moves(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(14))
        move_one = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Hip Bump Sweep",
            category_code="sweeps_closed",
            note="Post the hand",
            tags=["gi"],
        )
        move_two = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Knee Cut",
            category_code="transitions_passes",
            note="Crossface",
            tags=["pressure"],
        )
        training_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 16),
            move_ids=[move_one.id],
        )
        updated = await session_service.update_session(
            session,
            user_id=user.id,
            session_id=training_session.id,
            session_date=date(2026, 3, 17),
            move_ids=[move_one.id, move_two.id],
        )
        count = await session_service.count_practiced_moves(session, training_session.id)

    assert updated is not None
    assert updated.session_date == date(2026, 3, 17)
    assert count == 2


@pytest.mark.asyncio
async def test_delete_session_decrements_total_sessions(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(15))
        training_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 18),
            move_ids=[],
        )
        deleted = await session_service.delete_session(
            session,
            user_id=user.id,
            session_id=training_session.id,
        )
        progress = await user_service.get_progress(session, user.id)
        still_exists = await session_service.get_session(session, user_id=user.id, session_id=training_session.id)

    assert deleted is True
    assert progress.total_sessions == 0
    assert still_exists is None


@pytest.mark.asyncio
async def test_history_lists_practiced_moves(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(16))
        move_one = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Triangle",
            category_code="attacks_chokes",
            note="Angle off",
            tags=["gi"],
        )
        move_two = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Armbar",
            category_code="attacks_arm_locks",
            note="Clamp knees",
            tags=["gi"],
        )
        await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 19),
            move_ids=[move_one.id, move_two.id],
        )
        items = await history_service.get_history(session, user_id=user.id)

    session_item = next(item for item in items if item.kind == "session")
    assert "Practiced 2 moves" in session_item.text
    assert "- Triangle" in session_item.text
    assert "- Armbar" in session_item.text


@pytest.mark.asyncio
async def test_history_uses_singular_move_label(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(17))
        move = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Kimura",
            category_code="attacks_shoulder_locks",
            note="Trap the wrist",
            tags=["gi"],
        )
        await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 20),
            move_ids=[move.id],
        )
        items = await history_service.get_history(session, user_id=user.id)

    session_item = next(item for item in items if item.kind == "session")
    assert "Practiced 1 move" in session_item.text
    assert "Practiced 1 moves" not in session_item.text


@pytest.mark.asyncio
async def test_search_moves_supports_fuzzy_typos(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(18))
        await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Torreando Roll",
            category_code="transitions_passes",
            note="Outside angle",
            tags=["speed"],
        )
        await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Fake Step Knee Cut",
            category_code="transitions_passes",
            note="Crossface",
            tags=["pressure"],
        )

        typo_matches = await arsenal_service.search_moves(session, user.id, "toreadno")
        partial_matches = await arsenal_service.search_moves(session, user.id, "knee")

    assert typo_matches
    assert typo_matches[0].name == "Torreando Roll"
    assert partial_matches
    assert partial_matches[0].name == "Fake Step Knee Cut"


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
async def test_promotion_session_number_recalculates_after_session_date_change(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(23))
        first_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 10),
            move_ids=[],
        )
        await session_service.log_session(
            session,
            user_id=user.id,
            session_date=date(2026, 3, 20),
            move_ids=[],
        )
        promotion = await promotion_service.apply_promotion(
            session,
            user_id=user.id,
            promotion_date=date(2026, 3, 15),
            kind="stripe",
        )
        updated_session = await session_service.update_session(
            session,
            user_id=user.id,
            session_id=first_session.id,
            session_date=date(2026, 3, 25),
        )
        refreshed = await promotion_service.get_promotion(session, user_id=user.id, promotion_id=promotion.id)

    assert updated_session is not None
    assert refreshed is not None
    assert refreshed.session_number == 0


@pytest.mark.asyncio
async def test_update_and_delete_promotion_rebuild_progress(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(24))
        promotion = await promotion_service.apply_promotion(
            session,
            user_id=user.id,
            promotion_date=date(2026, 3, 11),
            kind="stripe",
        )
        updated = await promotion_service.update_promotion(
            session,
            user_id=user.id,
            promotion_id=promotion.id,
            belt="blue",
            stripes=0,
        )
        progress_after_update = await user_service.get_progress(session, user.id)
        progress_after_update_rank = (progress_after_update.belt, progress_after_update.stripes)
        deleted = await promotion_service.delete_promotion(session, user_id=user.id, promotion_id=promotion.id)
        progress_after_delete = await user_service.get_progress(session, user.id)
        progress_after_delete_rank = (progress_after_delete.belt, progress_after_delete.stripes)

    assert updated is not None
    assert updated.belt == "blue"
    assert progress_after_update_rank == ("blue", 0)
    assert deleted is True
    assert progress_after_delete_rank == ("white", 0)


@pytest.mark.asyncio
async def test_taxonomy_seeded(session_maker) -> None:
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, None)
    assert any(node.category.code == "standing" for node in categories)
    assert any(node.category.code == "guard" for node in categories)


@pytest.mark.asyncio
async def test_category_counts_include_descendants_for_current_user(session_maker) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, make_tg_user(21))
        other_user = await user_service.ensure_user(session, make_tg_user(22))
        await arsenal_service.create_move(
            session,
            user_id=user.id,
            name="Knee Cut",
            category_code="transitions_passes",
            note="Crossface",
            tags=["pressure"],
        )
        await arsenal_service.create_move(
            session,
            user_id=other_user.id,
            name="Toreando",
            category_code="transitions_passes",
            note="Angle in",
            tags=["speed"],
        )

        root_categories = await arsenal_service.list_child_categories(session, None, user_id=user.id)
        transition_categories = await arsenal_service.list_child_categories(session, "transitions", user_id=user.id)

    transitions_root = next(node for node in root_categories if node.category.code == "transitions")
    guard_passes = next(node for node in transition_categories if node.category.code == "transitions_passes")

    assert transitions_root.move_count == 1
    assert guard_passes.move_count == 1
