from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bjj_bot.services.arsenal import CategoryNode

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _navigation_row(back_callback: str | None = None) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if back_callback:
        row.append(InlineKeyboardButton(text="◀️ Back", callback_data=back_callback))
    row.append(InlineKeyboardButton(text="🏠 Open Menu", callback_data="menu:home"))
    return row


def prompt_keyboard(*, back_callback: str | None = None, skip_callback: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if skip_callback:
        rows.append([InlineKeyboardButton(text="⏭️ Skip", callback_data=skip_callback)])
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin:refresh")],
            [InlineKeyboardButton(text="🏠 Open Menu", callback_data="menu:home")],
        ]
    )


def main_menu_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🥷 Me", callback_data="menu:me")],
            [InlineKeyboardButton(text="🥋 Arsenal", callback_data="menu:arsenal")],
            [InlineKeyboardButton(text="📝 Log Session", callback_data="menu:log_session")],
        ]
    )


def me_menu_keyboard(*, belt_emoji: str = "🥋", is_black_belt: bool = False, competitor: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="ℹ️ Info", callback_data="me:info")],
        [InlineKeyboardButton(text=f"{belt_emoji} Show Belt", callback_data="me:show_belt")],
        [InlineKeyboardButton(text="⬆️ Upgrade", callback_data="me:upgrade")],
        [InlineKeyboardButton(text="🗓️ Session History", callback_data="me:sessions")],
        [InlineKeyboardButton(text="📈 Upgrade History", callback_data="me:upgrades")],
    ]
    if is_black_belt:
        label = "🏆 Competitor belt ✓" if competitor else "🏆 Competitor belt"
        rows.append([InlineKeyboardButton(text=label, callback_data="me:toggle_competitor")])
    rows.append(_navigation_row("menu:home"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def arsenal_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Library", callback_data="arsenal:browse:root")],
            [InlineKeyboardButton(text="➕ Add Move", callback_data="arsenal:add")],
            [InlineKeyboardButton(text="🔎 Search", callback_data="arsenal:search")],
            [InlineKeyboardButton(text="🕘 Recent Moves", callback_data="arsenal:recent")],
            _navigation_row("menu:home"),
        ]
    )


def format_quick_date_label(value: date) -> str:
    weekday = WEEKDAY_NAMES[value.weekday()]
    month = MONTH_NAMES[value.month - 1]
    return f"{weekday}, {value.day} {month}"


def date_picker_keyboard(
    prefix: str,
    *,
    today: date,
    custom_target: str | None = None,
    back_callback: str | None = None,
    extra_buttons: list[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    dates = [today - timedelta(days=offset) for offset in range(7)]
    rows = [
        [InlineKeyboardButton(text=format_quick_date_label(day), callback_data=f"{prefix}:{day.isoformat()}")]
        for day in dates
    ]
    if custom_target:
        rows.append([InlineKeyboardButton(text="🗓️ Other Date", callback_data=f"custom_date:{custom_target}")])
    for label, callback_data in extra_buttons or []:
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rank_picker_keyboard(
    *,
    options: list[tuple[str, str]],
    callback_prefix: str,
    back_callback: str | None,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"{callback_prefix}:{rank_key}")] for rank_key, label in options]
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upgrade_keyboard(options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return rank_picker_keyboard(options=options, callback_prefix="upgrade:set", back_callback="menu:me")


def session_builder_keyboard(
    *,
    selected_count: int,
    category_nodes: list[CategoryNode],
    moves: list[tuple[int, str, bool]],
    category_code: str | None,
    recent_moves: list[tuple[int, str, bool]] | None = None,
    recent: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for node in category_nodes:
        label = f"{node.category.name} ({node.move_count})"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"session:open:{node.category.code}")])
    for move_id, name, selected in moves:
        prefix = "✓ " if selected else ""
        rows.append([InlineKeyboardButton(text=f"{prefix}{name}", callback_data=f"session:toggle:{move_id}")])
    for move_id, name, selected in recent_moves or []:
        prefix = "✓ " if selected else ""
        rows.append([InlineKeyboardButton(text=f"🕘 {prefix}{name}", callback_data=f"session:toggle:{move_id}")])

    action_row: list[InlineKeyboardButton] = []
    if category_code is None and not recent:
        action_row.append(InlineKeyboardButton(text="🕘 Recent", callback_data="session:recent"))
    action_row.append(InlineKeyboardButton(text=f"💾 Save ({selected_count})", callback_data="session:save"))
    rows.append(action_row)
    rows.append([InlineKeyboardButton(text="➕ Add New Move", callback_data="session:add_move")])

    if category_code:
        back_callback = f"session:back:{category_code}"
    elif recent:
        back_callback = "session:root"
    else:
        back_callback = "menu:log_session"
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_picker_keyboard(
    *,
    category_nodes: list[CategoryNode],
    current_code: str | None,
    open_action: str,
    back_action: str | None,
    root_back_callback: str | None,
    select_leaf_action: str | None = None,
    edit_layout_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for node in category_nodes:
        if select_leaf_action and node.child_count == 0:
            callback_data = f"{select_leaf_action}:{node.category.code}"
        else:
            callback_data = f"{open_action}:{node.category.code}"
        count_label = f" ({node.move_count})" if node.move_count else ""
        rows.append([InlineKeyboardButton(text=f"{node.category.name}{count_label}", callback_data=callback_data)])

    if edit_layout_callback:
        rows.append([InlineKeyboardButton(text="✏️ Edit Layout", callback_data=edit_layout_callback)])
    back_callback = root_back_callback
    if current_code and back_action:
        back_callback = f"{back_action}:{current_code}"
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def library_edit_keyboard(
    *,
    category_nodes: list[CategoryNode],
    parent_slug: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton(text="➕ Add Group", callback_data=f"libcat:add:{parent_slug}")])
    for node in category_nodes:
        count_label = f" ({node.move_count})" if node.move_count else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{node.category.name}{count_label}",
                callback_data=f"libcat:edit:{node.category.code}",
            ),
            InlineKeyboardButton(text="✏️", callback_data=f"libcat:rename:{node.category.code}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"libcat:delete:{node.category.code}"),
        ])
    rows.append([InlineKeyboardButton(text="✅ Done Editing", callback_data=f"arsenal:browse:{parent_slug}")])
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_category_keyboard(code: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"libcat:delete_confirm:{code}")],
            _navigation_row(back_callback),
        ]
    )


def moves_keyboard(prefix: str, moves: list[tuple[int, str]], *, back_callback: str | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"{prefix}:{move_id}")] for move_id, name in moves]
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_keyboard(
    item_rows: list[tuple[str, str]],
    *,
    offset: int,
    has_previous: bool,
    has_next: bool,
    back_callback: str | None,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback_data)] for callback_data, label in item_rows]
    nav_row: list[InlineKeyboardButton] = []
    if has_previous:
        nav_row.append(InlineKeyboardButton(text="◀️ Newer", callback_data=f"history:{max(0, offset - 10)}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="Older ▶️", callback_data=f"history:{offset + 10}"))
    if nav_row:
        rows.append(nav_row)
    rows.append(_navigation_row(back_callback))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upgrade_history_keyboard(
    item_rows: list[tuple[str, str]],
    *,
    offset: int,
    has_previous: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback_data)] for callback_data, label in item_rows]
    nav_row: list[InlineKeyboardButton] = []
    if has_previous:
        nav_row.append(InlineKeyboardButton(text="◀️ Newer", callback_data=f"promotion_history:{max(0, offset - 10)}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="Older ▶️", callback_data=f"promotion_history:{offset + 10}"))
    if nav_row:
        rows.append(nav_row)
    rows.append(_navigation_row("menu:me"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def move_details_keyboard(move_id: int, category_code: str | None = None) -> InlineKeyboardMarkup:
    back = f"arsenal:browse:{category_code}" if category_code else "arsenal:home"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Edit Move", callback_data=f"move:edit:{move_id}")],
            [InlineKeyboardButton(text="📦 Move", callback_data=f"move:edit_group:{move_id}")],
            [InlineKeyboardButton(text="🗑️ Delete Move", callback_data=f"move:delete:{move_id}")],
            _navigation_row(back),
        ]
    )


def move_edit_keyboard(move_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏷️ Name", callback_data=f"move:edit_name:{move_id}")],
            [InlineKeyboardButton(text="🗂️ Group", callback_data=f"move:edit_group:{move_id}")],
            [InlineKeyboardButton(text="🔖 Tags", callback_data=f"move:edit_tags:{move_id}")],
            [InlineKeyboardButton(text="📝 Note", callback_data=f"move:edit_note:{move_id}")],
            _navigation_row(f"move:view:{move_id}"),
        ]
    )


def confirm_delete_move_keyboard(move_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"move:delete_confirm:{move_id}")],
            _navigation_row(f"move:view:{move_id}"),
        ]
    )


def session_details_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗓️ Edit Date", callback_data=f"logged_session:date:{session_id}")],
            [InlineKeyboardButton(text="⏱️ Edit Duration", callback_data=f"logged_session:duration:{session_id}")],
            [InlineKeyboardButton(text="🥋 Edit Moves", callback_data=f"logged_session:moves:{session_id}")],
            [InlineKeyboardButton(text="🗑️ Delete Session", callback_data=f"logged_session:delete:{session_id}")],
            _navigation_row("me:sessions"),
        ]
    )


def confirm_delete_session_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"logged_session:delete_confirm:{session_id}")],
            _navigation_row(f"logged_session:view:{session_id}"),
        ]
    )


def promotion_details_keyboard(promotion_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🥋 Edit Level", callback_data=f"promotion:rank:{promotion_id}")],
            [InlineKeyboardButton(text="🗓️ Edit Date", callback_data=f"promotion:date:{promotion_id}")],
            [InlineKeyboardButton(text="🗑️ Delete Upgrade", callback_data=f"promotion:delete:{promotion_id}")],
            _navigation_row("me:upgrades"),
        ]
    )


def confirm_delete_promotion_keyboard(promotion_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Delete", callback_data=f"promotion:delete_confirm:{promotion_id}")],
            _navigation_row(f"promotion:view:{promotion_id}"),
        ]
    )


def session_saved_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Edit Session", callback_data=f"logged_session:view:{session_id}")],
            _navigation_row("menu:home"),
        ]
    )
