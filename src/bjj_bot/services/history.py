from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import Promotion, SessionPracticedMove, TrainingSession
from bjj_bot.visuals import build_rank_text


@dataclass(slots=True)
class HistoryItem:
    kind: str
    date: date
    created_at: datetime
    text: str


async def get_history(session: AsyncSession, *, user_id: int, offset: int = 0, limit: int = 10) -> list[HistoryItem]:
    session_rows = await session.execute(
        select(
            TrainingSession.id,
            TrainingSession.session_date,
            TrainingSession.created_at,
            func.count(SessionPracticedMove.id),
        )
        .outerjoin(SessionPracticedMove, SessionPracticedMove.session_id == TrainingSession.id)
        .where(TrainingSession.user_id == user_id)
        .group_by(TrainingSession.id)
    )
    promotion_rows = await session.execute(
        select(Promotion.id, Promotion.promotion_date, Promotion.created_at, Promotion.belt, Promotion.stripes, Promotion.session_number)
        .where(Promotion.user_id == user_id)
    )

    items: list[HistoryItem] = []
    for session_id, session_date, created_at, move_count in session_rows.all():
        items.append(
            HistoryItem(
                kind="session",
                date=session_date,
                created_at=created_at,
                text=f"+1 session · {int(move_count)} moves",
            )
        )
    for _promotion_id, promotion_date, created_at, belt, stripes, session_number in promotion_rows.all():
        items.append(
            HistoryItem(
                kind="promotion",
                date=promotion_date,
                created_at=created_at,
                text=f"{build_rank_text(belt, stripes)} · earned at session {session_number}",
            )
        )

    items.sort(key=lambda item: (item.date, item.created_at), reverse=True)
    return items[offset : offset + limit]
