from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bjj_bot.services.arsenal import CategoryNode


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Log Session"), KeyboardButton(text="Upgrade")],
            [KeyboardButton(text="My Progress"), KeyboardButton(text="History")],
            [KeyboardButton(text="Arsenal")],
        ],
        resize_keyboard=True,
    )


def date_picker_keyboard(prefix: str) -> InlineKeyboardMarkup:
    today = date.today()
    dates = [today - timedelta(days=offset) for offset in range(4)]
    rows = [
        [InlineKeyboardButton(text=day.strftime("%b %d"), callback_data=f"{prefix}:{day.isoformat()}")]
        for day in dates
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promotion_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="+ Stripe", callback_data="upgrade:stripe")],
            [InlineKeyboardButton(text="New Belt", callback_data="upgrade:belt")],
        ]
    )


def session_builder_keyboard(
    *,
    selected_count: int,
    category_nodes: list[CategoryNode],
    moves: list[tuple[int, str, bool]],
    category_code: str | None,
    recent_moves: list[tuple[int, str, bool]] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for node in category_nodes:
        label = f"{node.category.name} ({node.move_count})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"session:open:{node.category.code}")])
    for move_id, name, selected in moves:
        prefix = "✓ " if selected else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}{name}", callback_data=f"session:toggle:{move_id}")])
    if recent_moves:
        for move_id, name, selected in recent_moves:
            prefix = "✓ " if selected else ""
            rows.append(
                [InlineKeyboardButton(text=f"Recent · {prefix}{name}", callback_data=f"session:toggle:{move_id}")]
            )
    nav_row = []
    if category_code:
        nav_row.append(InlineKeyboardButton(text="Back", callback_data=f"session:back:{category_code}"))
    else:
        nav_row.append(InlineKeyboardButton(text="Recent", callback_data="session:recent"))
    nav_row.append(InlineKeyboardButton(text=f"Save ({selected_count})", callback_data="session:save"))
    rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="Add New Move", callback_data="session:add_move")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def arsenal_root_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Browse Groups", callback_data="arsenal:browse:root")],
            [InlineKeyboardButton(text="Add Move", callback_data="arsenal:add")],
            [InlineKeyboardButton(text="Search", callback_data="arsenal:search")],
            [InlineKeyboardButton(text="Recent Moves", callback_data="arsenal:recent")],
        ]
    )


def category_picker_keyboard(
    *,
    category_nodes: list[CategoryNode],
    current_code: str | None,
    use_action: str,
    open_action: str,
    back_action: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if current_code:
        rows.append([InlineKeyboardButton(text="Use This Group", callback_data=f"{use_action}:{current_code}")])
        rows.append([InlineKeyboardButton(text="Back", callback_data=f"{back_action}:{current_code}")])
    for node in category_nodes:
        rows.append([InlineKeyboardButton(text=node.category.name, callback_data=f"{open_action}:{node.category.code}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moves_keyboard(prefix: str, moves: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"{prefix}:{move_id}")]
        for move_id, name in moves
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def move_details_keyboard(move_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Edit Note", callback_data=f"move:note:{move_id}")],
            [InlineKeyboardButton(text="Arsenal Home", callback_data="arsenal:home")],
        ]
    )


def history_keyboard(next_offset: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="More", callback_data=f"history:{next_offset}")]]
    )
