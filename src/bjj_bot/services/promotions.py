from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import AthleteProgress, Promotion
from bjj_bot.services.rank import RankError, RankState, add_stripe, promote_belt


async def apply_promotion(
    session: AsyncSession,
    *,
    user_id: int,
    promotion_date: date,
    kind: str,
) -> Promotion:
    progress = await session.scalar(select(AthleteProgress).where(AthleteProgress.user_id == user_id))
    if progress is None:
        raise RankError("Progress not initialized")

    current = RankState(belt=progress.belt, stripes=progress.stripes)
    if kind == "stripe":
        updated = add_stripe(current)
    elif kind == "belt":
        updated = promote_belt(current)
    else:
        raise RankError("Unknown promotion type")

    progress.belt = updated.belt
    progress.stripes = updated.stripes
    progress.last_updated_at = datetime.now(UTC)

    promotion = Promotion(
        user_id=user_id,
        promotion_date=promotion_date,
        belt=updated.belt,
        stripes=updated.stripes,
        session_number=progress.total_sessions,
    )
    session.add(promotion)
    await session.commit()
    await session.refresh(promotion)
    return promotion
