from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import ArsenalMove, Promotion, SessionPracticedMove, TrainingSession
from bjj_bot.visuals import build_rank_text


@dataclass(slots=True)
class HistoryItem:
    entity_id: int
    kind: str
    date: date
    created_at: datetime
    text: str


async def _session_rows(session: AsyncSession, *, user_id: int) -> tuple[list[tuple[int, date, datetime, int]], dict[int, list[str]]]:
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
    session_move_rows = await session.execute(
        select(SessionPracticedMove.session_id, ArsenalMove.name)
        .join(ArsenalMove, ArsenalMove.id == SessionPracticedMove.move_id)
        .join(TrainingSession, TrainingSession.id == SessionPracticedMove.session_id)
        .where(TrainingSession.user_id == user_id)
        .order_by(SessionPracticedMove.session_id, ArsenalMove.name)
    )

    moves_by_session: dict[int, list[str]] = {}
    for session_id, move_name in session_move_rows.all():
        moves_by_session.setdefault(session_id, []).append(move_name)
    return list(session_rows.all()), moves_by_session


def _build_session_items(
    session_rows: list[tuple[int, date, datetime, int]],
    moves_by_session: dict[int, list[str]],
) -> list[HistoryItem]:
    items: list[HistoryItem] = []
    for session_id, session_date, created_at, move_count in session_rows:
        move_names = moves_by_session.get(session_id, [])
        move_label = "move" if int(move_count) == 1 else "moves"
        lines = [f"Practiced {int(move_count)} {move_label}"]
        if move_names:
            lines.extend(f"- {move_name}" for move_name in move_names)
        items.append(
            HistoryItem(
                entity_id=session_id,
                kind="session",
                date=session_date,
                created_at=created_at,
                text="\n".join(lines),
            )
        )
    items.sort(key=lambda item: (item.date, item.created_at), reverse=True)
    return items


async def _promotion_items(session: AsyncSession, *, user_id: int) -> list[HistoryItem]:
    return await _promotion_items_with_visuals(session, user_id=user_id)


async def _promotion_items_with_visuals(
    session: AsyncSession,
    *,
    user_id: int,
    belt_emoji_map: dict[str, str] | None = None,
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> list[HistoryItem]:
    promotion_rows = await session.execute(
        select(Promotion.id, Promotion.promotion_date, Promotion.created_at, Promotion.belt, Promotion.stripes, Promotion.session_number)
        .where(Promotion.user_id == user_id)
    )

    items: list[HistoryItem] = []
    for promotion_id, promotion_date, created_at, belt, stripes, session_number in promotion_rows.all():
        items.append(
            HistoryItem(
                entity_id=promotion_id,
                kind="promotion",
                date=promotion_date,
                created_at=created_at,
                text=f"{build_rank_text(belt, stripes, belt_emoji_map, rank_custom_emoji_map)} · earned at session {session_number}",
            )
        )
    items.sort(key=lambda item: (item.date, item.created_at), reverse=True)
    return items


async def get_session_history(
    session: AsyncSession,
    *,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
) -> list[HistoryItem]:
    session_rows, moves_by_session = await _session_rows(session, user_id=user_id)
    return _build_session_items(session_rows, moves_by_session)[offset : offset + limit]


async def get_promotion_history(
    session: AsyncSession,
    *,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
    belt_emoji_map: dict[str, str] | None = None,
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> list[HistoryItem]:
    return (
        await _promotion_items_with_visuals(
            session,
            user_id=user_id,
            belt_emoji_map=belt_emoji_map,
            rank_custom_emoji_map=rank_custom_emoji_map,
        )
    )[offset : offset + limit]


async def get_history(
    session: AsyncSession,
    *,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
    belt_emoji_map: dict[str, str] | None = None,
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> list[HistoryItem]:
    session_rows, moves_by_session = await _session_rows(session, user_id=user_id)
    items = _build_session_items(session_rows, moves_by_session)
    items.extend(
        await _promotion_items_with_visuals(
            session,
            user_id=user_id,
            belt_emoji_map=belt_emoji_map,
            rank_custom_emoji_map=rank_custom_emoji_map,
        )
    )
    items.sort(key=lambda item: (item.date, item.created_at), reverse=True)
    return items[offset : offset + limit]
