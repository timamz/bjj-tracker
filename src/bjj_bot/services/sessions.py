from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import AthleteProgress, ArsenalMove, SessionPracticedMove, TrainingSession


class SessionError(ValueError):
    pass


async def log_session(
    session: AsyncSession,
    *,
    user_id: int,
    session_date: date,
    move_ids: list[int],
) -> TrainingSession:
    if move_ids:
        result = await session.execute(
            select(ArsenalMove.id).where(ArsenalMove.user_id == user_id, ArsenalMove.id.in_(move_ids))
        )
        found_ids = {row[0] for row in result.all()}
        missing = set(move_ids) - found_ids
        if missing:
            raise SessionError("One or more selected moves do not belong to this user")

    progress = await session.scalar(select(AthleteProgress).where(AthleteProgress.user_id == user_id))
    if progress is None:
        raise SessionError("Progress not initialized")

    training_session = TrainingSession(user_id=user_id, session_date=session_date)
    session.add(training_session)
    await session.flush()

    unique_ids = list(dict.fromkeys(move_ids))
    for move_id in unique_ids:
        session.add(SessionPracticedMove(session_id=training_session.id, move_id=move_id))

    progress.total_sessions += 1
    progress.last_updated_at = datetime.now(UTC)
    from bjj_bot.services import promotions as promotion_service

    await promotion_service.recalculate_session_numbers(session, user_id=user_id)
    await session.commit()
    await session.refresh(training_session)
    return training_session


async def count_practiced_moves(session: AsyncSession, training_session_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(SessionPracticedMove.id)).where(
                SessionPracticedMove.session_id == training_session_id
            )
        )
        or 0
    )


async def get_session(session: AsyncSession, *, user_id: int, session_id: int) -> TrainingSession | None:
    return await session.scalar(
        select(TrainingSession)
        .where(TrainingSession.id == session_id, TrainingSession.user_id == user_id)
        .options(selectinload(TrainingSession.practiced_moves))
    )


async def get_session_move_ids(session: AsyncSession, *, user_id: int, session_id: int) -> list[int]:
    training_session = await get_session(session, user_id=user_id, session_id=session_id)
    if training_session is None:
        return []
    return [row.move_id for row in training_session.practiced_moves]


async def update_session(
    session: AsyncSession,
    *,
    user_id: int,
    session_id: int,
    session_date: date | None = None,
    move_ids: list[int] | None = None,
) -> TrainingSession | None:
    training_session = await get_session(session, user_id=user_id, session_id=session_id)
    if training_session is None:
        return None

    if session_date is not None:
        training_session.session_date = session_date

    if move_ids is not None:
        if move_ids:
            result = await session.execute(
                select(ArsenalMove.id).where(ArsenalMove.user_id == user_id, ArsenalMove.id.in_(move_ids))
            )
            found_ids = {row[0] for row in result.all()}
            missing = set(move_ids) - found_ids
            if missing:
                raise SessionError("One or more selected moves do not belong to this user")
        await session.execute(delete(SessionPracticedMove).where(SessionPracticedMove.session_id == session_id))
        unique_ids = list(dict.fromkeys(move_ids))
        for move_id in unique_ids:
            session.add(SessionPracticedMove(session_id=session_id, move_id=move_id))

    from bjj_bot.services import promotions as promotion_service

    await promotion_service.recalculate_session_numbers(session, user_id=user_id)
    await session.commit()
    return await get_session(session, user_id=user_id, session_id=session_id)


async def delete_session(session: AsyncSession, *, user_id: int, session_id: int) -> bool:
    training_session = await get_session(session, user_id=user_id, session_id=session_id)
    if training_session is None:
        return False

    progress = await session.scalar(select(AthleteProgress).where(AthleteProgress.user_id == user_id))
    if progress is None:
        raise SessionError("Progress not initialized")

    await session.execute(delete(SessionPracticedMove).where(SessionPracticedMove.session_id == session_id))
    await session.delete(training_session)
    progress.total_sessions = max(0, progress.total_sessions - 1)
    progress.last_updated_at = datetime.now(UTC)
    from bjj_bot.services import promotions as promotion_service

    await promotion_service.recalculate_session_numbers(session, user_id=user_id)
    await session.commit()
    return True


async def first_session_date(session: AsyncSession, *, user_id: int) -> date | None:
    return await session.scalar(
        select(func.min(TrainingSession.session_date)).where(TrainingSession.user_id == user_id)
    )


async def count_sessions_since(session: AsyncSession, *, user_id: int, since_date: date) -> int:
    return int(
        await session.scalar(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id == user_id,
                TrainingSession.session_date >= since_date,
            )
        )
        or 0
    )
