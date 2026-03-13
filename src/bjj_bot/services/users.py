from __future__ import annotations

from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bjj_bot.models import AthleteProgress, Belt, User


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.id))
    if user is None:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )
        session.add(user)
        await session.flush()
        session.add(AthleteProgress(user_id=user.id, belt=Belt.WHITE.value, stripes=0, total_sessions=0))
        await session.commit()
        await session.refresh(user)
        return user

    user.username = telegram_user.username
    user.first_name = telegram_user.first_name
    user.last_name = telegram_user.last_name
    await session.commit()
    return user


async def get_progress(session: AsyncSession, user_id: int) -> AthleteProgress:
    progress = await session.scalar(select(AthleteProgress).where(AthleteProgress.user_id == user_id))
    if progress is None:
        progress = AthleteProgress(user_id=user_id, belt=Belt.WHITE.value, stripes=0, total_sessions=0)
        session.add(progress)
        await session.commit()
        await session.refresh(progress)
    return progress

