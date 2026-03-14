from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import AthleteProgress, Belt, Promotion, TrainingSession
from bjj_bot.services.rank import RankError, RankState, add_stripe, promote_belt, rank_position, set_rank


async def _progress_or_error(session: AsyncSession, *, user_id: int) -> AthleteProgress:
    progress = await session.scalar(select(AthleteProgress).where(AthleteProgress.user_id == user_id))
    if progress is None:
        raise RankError("Progress not initialized")
    return progress


async def _session_count_at_date(session: AsyncSession, *, user_id: int, promotion_date: date) -> int:
    return int(
        await session.scalar(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.user_id == user_id,
                TrainingSession.session_date <= promotion_date,
            )
        )
        or 0
    )


async def _rebuild_progress(session: AsyncSession, *, user_id: int) -> None:
    progress = await _progress_or_error(session, user_id=user_id)
    latest_promotion = await session.scalar(
        select(Promotion)
        .where(Promotion.user_id == user_id)
        .order_by(Promotion.promotion_date.desc(), Promotion.created_at.desc(), Promotion.id.desc())
        .limit(1)
    )
    if latest_promotion is None:
        progress.belt = Belt.WHITE.value
        progress.stripes = 0
    else:
        progress.belt = latest_promotion.belt
        progress.stripes = latest_promotion.stripes
    progress.last_updated_at = datetime.now(UTC)


async def recalculate_session_numbers(session: AsyncSession, *, user_id: int) -> None:
    promotions = list(
        (
            await session.execute(
                select(Promotion)
                .where(Promotion.user_id == user_id)
                .order_by(Promotion.promotion_date, Promotion.created_at, Promotion.id)
            )
        ).scalars()
    )
    for promotion in promotions:
        promotion.session_number = await _session_count_at_date(
            session,
            user_id=user_id,
            promotion_date=promotion.promotion_date,
        )


async def list_promotions(
    session: AsyncSession,
    *,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
) -> list[Promotion]:
    return list(
        (
            await session.execute(
                select(Promotion)
                .where(Promotion.user_id == user_id)
                .order_by(Promotion.promotion_date.desc(), Promotion.created_at.desc(), Promotion.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
    )


async def count_promotions(session: AsyncSession, *, user_id: int) -> int:
    return int(await session.scalar(select(func.count(Promotion.id)).where(Promotion.user_id == user_id)) or 0)


async def get_promotion(session: AsyncSession, *, user_id: int, promotion_id: int) -> Promotion | None:
    return await session.scalar(
        select(Promotion).where(Promotion.user_id == user_id, Promotion.id == promotion_id)
    )


async def apply_promotion(
    session: AsyncSession,
    *,
    user_id: int,
    promotion_date: date,
    kind: str,
) -> Promotion:
    progress = await _progress_or_error(session, user_id=user_id)
    current = RankState(belt=progress.belt, stripes=progress.stripes)
    if kind == "stripe":
        updated = add_stripe(current)
    elif kind == "belt":
        updated = promote_belt(current)
    else:
        raise RankError("Unknown promotion type")

    promotion = Promotion(
        user_id=user_id,
        promotion_date=promotion_date,
        belt=updated.belt,
        stripes=updated.stripes,
        session_number=await _session_count_at_date(session, user_id=user_id, promotion_date=promotion_date),
    )
    session.add(promotion)
    await recalculate_session_numbers(session, user_id=user_id)
    await _rebuild_progress(session, user_id=user_id)
    await session.commit()
    await session.refresh(promotion)
    return promotion


async def set_promotion_rank(
    session: AsyncSession,
    *,
    user_id: int,
    promotion_date: date,
    belt: str,
    stripes: int,
) -> Promotion:
    progress = await _progress_or_error(session, user_id=user_id)
    current = RankState(belt=progress.belt, stripes=progress.stripes)
    updated = set_rank(current, RankState(belt=belt, stripes=stripes))

    promotion = Promotion(
        user_id=user_id,
        promotion_date=promotion_date,
        belt=updated.belt,
        stripes=updated.stripes,
        session_number=await _session_count_at_date(session, user_id=user_id, promotion_date=promotion_date),
    )
    session.add(promotion)
    await recalculate_session_numbers(session, user_id=user_id)
    await _rebuild_progress(session, user_id=user_id)
    await session.commit()
    await session.refresh(promotion)
    return promotion


async def update_promotion(
    session: AsyncSession,
    *,
    user_id: int,
    promotion_id: int,
    promotion_date: date | None = None,
    belt: str | None = None,
    stripes: int | None = None,
) -> Promotion | None:
    promotion = await get_promotion(session, user_id=user_id, promotion_id=promotion_id)
    if promotion is None:
        return None

    next_belt = belt if belt is not None else promotion.belt
    next_stripes = stripes if stripes is not None else promotion.stripes
    rank_position(RankState(belt=next_belt, stripes=next_stripes))

    if promotion_date is not None:
        promotion.promotion_date = promotion_date
    promotion.belt = next_belt
    promotion.stripes = next_stripes
    promotion.session_number = await _session_count_at_date(
        session,
        user_id=user_id,
        promotion_date=promotion.promotion_date,
    )
    await recalculate_session_numbers(session, user_id=user_id)
    await _rebuild_progress(session, user_id=user_id)
    await session.commit()
    await session.refresh(promotion)
    return promotion


async def delete_promotion(session: AsyncSession, *, user_id: int, promotion_id: int) -> bool:
    promotion = await get_promotion(session, user_id=user_id, promotion_id=promotion_id)
    if promotion is None:
        return False

    await session.delete(promotion)
    await recalculate_session_numbers(session, user_id=user_id)
    await _rebuild_progress(session, user_id=user_id)
    await session.commit()
    return True
