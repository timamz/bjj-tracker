from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
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
