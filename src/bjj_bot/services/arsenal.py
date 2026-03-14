from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bjj_bot.models import ArsenalCategory, ArsenalMove, MoveTag, SessionPracticedMove


@dataclass(slots=True)
class CategoryNode:
    category: ArsenalCategory
    child_count: int
    move_count: int


def normalize_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for tag in raw.split(","):
        clean = tag.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _normalize_search_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _fuzzy_score(query: str, candidate: str) -> float:
    normalized_query = _normalize_search_text(query)
    normalized_candidate = _normalize_search_text(candidate)
    if not normalized_query or not normalized_candidate:
        return 0.0

    if normalized_query in normalized_candidate:
        return 2.0 + (len(normalized_query) / max(len(normalized_candidate), 1))

    query_tokens = normalized_query.split()
    candidate_tokens = normalized_candidate.split()

    token_scores: list[float] = []
    for query_token in query_tokens:
        best_token_score = max(
            SequenceMatcher(None, query_token, candidate_token).ratio()
            for candidate_token in candidate_tokens
        )
        token_scores.append(best_token_score)

    overall_score = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
    return max(overall_score, sum(token_scores) / len(token_scores))


async def list_child_categories(
    session: AsyncSession,
    parent_code: str | None,
    *,
    user_id: int | None = None,
) -> list[CategoryNode]:
    category_rows = await session.execute(
        select(ArsenalCategory).order_by(ArsenalCategory.sort_order, ArsenalCategory.name)
    )
    categories = list(category_rows.scalars())

    by_parent: dict[str | None, list[ArsenalCategory]] = defaultdict(list)
    for category in categories:
        by_parent[category.parent_code].append(category)

    move_count_query = select(ArsenalMove.category_code, func.count(ArsenalMove.id)).group_by(ArsenalMove.category_code)
    if user_id is not None:
        move_count_query = move_count_query.where(ArsenalMove.user_id == user_id)
    move_count_rows = await session.execute(move_count_query)
    direct_move_counts = {category_code: int(count) for category_code, count in move_count_rows.all()}

    aggregated_move_counts: dict[str, int] = {}

    def count_descendant_moves(category_code: str) -> int:
        if category_code in aggregated_move_counts:
            return aggregated_move_counts[category_code]
        total = direct_move_counts.get(category_code, 0)
        for child in by_parent.get(category_code, []):
            total += count_descendant_moves(child.code)
        aggregated_move_counts[category_code] = total
        return total

    return [
        CategoryNode(
            category=category,
            child_count=len(by_parent.get(category.code, [])),
            move_count=count_descendant_moves(category.code),
        )
        for category in by_parent.get(parent_code, [])
    ]


async def get_category(session: AsyncSession, code: str) -> ArsenalCategory | None:
    return await session.get(ArsenalCategory, code)


async def get_category_path(session: AsyncSession, code: str | None) -> list[ArsenalCategory]:
    if code is None:
        return []
    all_categories = (
        await session.execute(select(ArsenalCategory).order_by(ArsenalCategory.sort_order, ArsenalCategory.name))
    ).scalars()
    by_code = {category.code: category for category in all_categories}
    path: list[ArsenalCategory] = []
    current = by_code.get(code)
    while current is not None:
        path.append(current)
        current = by_code.get(current.parent_code) if current.parent_code else None
    return list(reversed(path))


async def list_moves_in_category(session: AsyncSession, user_id: int, category_code: str) -> list[ArsenalMove]:
    result = await session.execute(
        select(ArsenalMove)
        .where(ArsenalMove.user_id == user_id, ArsenalMove.category_code == category_code)
        .options(selectinload(ArsenalMove.tags))
        .order_by(ArsenalMove.name)
    )
    return list(result.scalars())


async def list_recent_moves(session: AsyncSession, user_id: int, limit: int = 8) -> list[ArsenalMove]:
    result = await session.execute(
        select(ArsenalMove)
        .where(ArsenalMove.user_id == user_id)
        .options(selectinload(ArsenalMove.tags))
        .order_by(ArsenalMove.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def search_moves(session: AsyncSession, user_id: int, query: str, limit: int = 12) -> list[ArsenalMove]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []

    result = await session.execute(
        select(ArsenalMove)
        .where(ArsenalMove.user_id == user_id)
        .options(selectinload(ArsenalMove.tags))
        .order_by(ArsenalMove.updated_at.desc(), ArsenalMove.name)
    )
    scored_moves: list[tuple[float, ArsenalMove]] = []
    for move in result.scalars():
        score = _fuzzy_score(normalized_query, move.name)
        if score >= 0.6:
            scored_moves.append((score, move))

    scored_moves.sort(key=lambda item: (-item[0], item[1].name.lower(), -item[1].updated_at.timestamp()))
    return [move for _score, move in scored_moves[:limit]]


async def get_move(session: AsyncSession, user_id: int, move_id: int) -> ArsenalMove | None:
    return await session.scalar(
        select(ArsenalMove)
        .where(ArsenalMove.id == move_id, ArsenalMove.user_id == user_id)
        .options(selectinload(ArsenalMove.tags))
    )


async def create_move(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    category_code: str,
    note: str = "",
    tags: list[str] | None = None,
) -> ArsenalMove:
    move = ArsenalMove(
        user_id=user_id,
        name=name.strip(),
        category_code=category_code,
        note=note.strip(),
    )
    session.add(move)
    await session.flush()
    for tag in tags or []:
        session.add(MoveTag(move_id=move.id, value=tag))
    await session.commit()
    return await get_move(session, user_id, move.id)  # type: ignore[return-value]


async def update_move_note(session: AsyncSession, *, user_id: int, move_id: int, note: str) -> ArsenalMove | None:
    move = await get_move(session, user_id, move_id)
    if move is None:
        return None
    move.note = note.strip()
    move.updated_at = datetime.now(UTC)
    await session.commit()
    return move


async def update_move(
    session: AsyncSession,
    *,
    user_id: int,
    move_id: int,
    name: str | None = None,
    category_code: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
) -> ArsenalMove | None:
    move = await get_move(session, user_id, move_id)
    if move is None:
        return None
    if name is not None:
        move.name = name.strip()
    if category_code is not None:
        move.category_code = category_code
    if note is not None:
        move.note = note.strip()
    if tags is not None:
        move.tags.clear()
        for tag in tags:
            move.tags.append(MoveTag(value=tag))
    move.updated_at = datetime.now(UTC)
    await session.commit()
    return await get_move(session, user_id, move.id)


async def delete_move(session: AsyncSession, *, user_id: int, move_id: int) -> bool:
    move = await get_move(session, user_id, move_id)
    if move is None:
        return False
    await session.execute(delete(SessionPracticedMove).where(SessionPracticedMove.move_id == move.id))
    await session.delete(move)
    await session.commit()
    return True


def format_move_details(move: ArsenalMove, category_name: str | None = None) -> str:
    tags = ", ".join(tag.value for tag in move.tags) if move.tags else "none"
    note = move.note or "none"
    category_line = category_name or move.category_code
    return "\n".join(
        [
            f"{move.name}",
            f"group: {category_line}",
            f"tags: {tags}",
            f"note: {note}",
        ]
    )
