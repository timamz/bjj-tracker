from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import ArsenalMove, TrainingSession, User


@dataclass(slots=True)
class AdminStats:
    total_users: int
    new_users_week: int
    new_users_month: int
    active_users_30d: int
    total_sessions: int
    total_moves: int


async def get_admin_stats(session: AsyncSession) -> AdminStats:
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    month_ago_date = month_ago.date()

    total_users = await session.scalar(select(func.count(User.id))) or 0
    new_users_week = await session.scalar(
        select(func.count(User.id)).where(User.created_at >= week_ago)
    ) or 0
    new_users_month = await session.scalar(
        select(func.count(User.id)).where(User.created_at >= month_ago)
    ) or 0
    active_users_30d = await session.scalar(
        select(func.count(distinct(TrainingSession.user_id))).where(
            TrainingSession.session_date >= month_ago_date
        )
    ) or 0
    total_sessions = await session.scalar(select(func.count(TrainingSession.id))) or 0
    total_moves = await session.scalar(select(func.count(ArsenalMove.id))) or 0

    return AdminStats(
        total_users=total_users,
        new_users_week=new_users_week,
        new_users_month=new_users_month,
        active_users_30d=active_users_30d,
        total_sessions=total_sessions,
        total_moves=total_moves,
    )
