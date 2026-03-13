from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bjj_bot.models import ArsenalCategory, ArsenalMove, MoveTag


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


async def list_child_categories(session: AsyncSession, parent_code: str | None) -> list[CategoryNode]:
    child_count_subquery = (
        select(ArsenalCategory.parent_code, func.count(ArsenalCategory.code).label("count"))
        .group_by(ArsenalCategory.parent_code)
        .subquery()
    )
    move_count_subquery = (
        select(ArsenalMove.category_code, func.count(ArsenalMove.id).label("count"))
        .group_by(ArsenalMove.category_code)
        .subquery()
    )
    query: Select[tuple[ArsenalCategory, int | None, int | None]] = (
        select(
            ArsenalCategory,
            child_count_subquery.c.count,
            move_count_subquery.c.count,
        )
        .outerjoin(child_count_subquery, child_count_subquery.c.parent_code == ArsenalCategory.code)
        .outerjoin(move_count_subquery, move_count_subquery.c.category_code == ArsenalCategory.code)
        .where(ArsenalCategory.parent_code == parent_code)
        .order_by(ArsenalCategory.sort_order, ArsenalCategory.name)
    )
    rows = await session.execute(query)
    return [
        CategoryNode(category=row[0], child_count=int(row[1] or 0), move_count=int(row[2] or 0))
        for row in rows.all()
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
    result = await session.execute(
        select(ArsenalMove)
        .where(ArsenalMove.user_id == user_id, ArsenalMove.name.ilike(f"%{query.strip()}%"))
        .options(selectinload(ArsenalMove.tags))
        .order_by(ArsenalMove.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


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

