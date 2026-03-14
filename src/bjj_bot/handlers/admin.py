from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bjj_bot.config import Settings
from bjj_bot.keyboards import admin_panel_keyboard
from bjj_bot.services import admin as admin_service
from bjj_bot.services.admin import AdminStats

router = Router()


def _is_owner(telegram_id: int, settings: Settings) -> bool:
    return settings.owner_id is not None and telegram_id == settings.owner_id


def _format_stats(stats: AdminStats) -> str:
    return (
        "📊 Admin Panel\n\n"
        "👥 Users\n"
        f"  Total: {stats.total_users}\n"
        f"  New this week: {stats.new_users_week}\n"
        f"  New this month: {stats.new_users_month}\n"
        f"  Active last 30d: {stats.active_users_30d}\n\n"
        "📋 Content\n"
        f"  Sessions logged: {stats.total_sessions}\n"
        f"  Arsenal moves: {stats.total_moves}"
    )


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    settings: Settings,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_owner(message.from_user.id, settings):
        return
    async with session_maker() as session:
        stats = await admin_service.get_admin_stats(session)
    await message.answer(_format_stats(stats), reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:refresh")
async def admin_refresh(
    callback: CallbackQuery,
    settings: Settings,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    if not _is_owner(callback.from_user.id, settings):
        await callback.answer()
        return
    async with session_maker() as session:
        stats = await admin_service.get_admin_stats(session)
    await callback.message.edit_text(_format_stats(stats), reply_markup=admin_panel_keyboard())
    await callback.answer("Refreshed")
