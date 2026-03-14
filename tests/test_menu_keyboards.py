from datetime import date

from bjj_bot.keyboards import (
    arsenal_menu_keyboard,
    category_picker_keyboard,
    date_picker_keyboard,
    history_keyboard,
    main_menu_actions_keyboard,
    me_menu_keyboard,
    rank_picker_keyboard,
    session_builder_keyboard,
    upgrade_keyboard,
)
from bjj_bot.services.arsenal import CategoryNode
from bjj_bot.models import ArsenalCategory


def test_main_menu_actions_are_inline_with_emojis() -> None:
    keyboard = main_menu_actions_keyboard()
    assert keyboard.inline_keyboard[0][0].text == "🥷 Me"
    assert keyboard.inline_keyboard[1][0].text == "🥋 Arsenal"
    assert keyboard.inline_keyboard[2][0].text == "📝 Log Session"


def test_me_menu_has_upgrade_history_and_navigation_row() -> None:
    keyboard = me_menu_keyboard()
    assert keyboard.inline_keyboard[0][0].text == "ℹ️ Info"
    assert keyboard.inline_keyboard[1][0].text == "⬆️ Upgrade"
    assert keyboard.inline_keyboard[2][0].text == "🗓️ Session History"
    assert keyboard.inline_keyboard[3][0].text == "🧾 Upgrade History"
    assert keyboard.inline_keyboard[-1][0].text == "◀️ Back"
    assert keyboard.inline_keyboard[-1][1].text == "🏠 Open Menu"


def test_arsenal_menu_has_section_actions() -> None:
    keyboard = arsenal_menu_keyboard()
    assert keyboard.inline_keyboard[0][0].text == "📚 Library"
    assert keyboard.inline_keyboard[1][0].callback_data == "arsenal:add"
    assert keyboard.inline_keyboard[2][0].callback_data == "arsenal:search"
    assert keyboard.inline_keyboard[3][0].callback_data == "arsenal:recent"


def test_date_picker_uses_other_date_and_navigation() -> None:
    keyboard = date_picker_keyboard(
        "session_date",
        today=date(2026, 3, 14),
        custom_target="session",
        back_callback="menu:home",
    )
    assert keyboard.inline_keyboard[-2][0].text == "🗓️ Other Date"
    assert keyboard.inline_keyboard[-1][0].text == "◀️ Back"
    assert keyboard.inline_keyboard[-1][1].text == "🏠 Open Menu"


def test_upgrade_keyboard_has_rank_rows_and_navigation() -> None:
    keyboard = upgrade_keyboard([("blue:2", "🟦🟦🟦 ⚪⚪")])
    assert keyboard.inline_keyboard[0][0].callback_data == "upgrade:set:blue:2"
    assert keyboard.inline_keyboard[-1][0].text == "◀️ Back"
    assert keyboard.inline_keyboard[-1][1].text == "🏠 Open Menu"


def test_rank_picker_uses_custom_prefix() -> None:
    keyboard = rank_picker_keyboard(
        options=[("white:1", "⬜⬜⬜ ⚪")],
        callback_prefix="promotion:set:5",
        back_callback="promotion:view:5",
    )
    assert keyboard.inline_keyboard[0][0].callback_data == "promotion:set:5:white:1"
    assert keyboard.inline_keyboard[-1][0].callback_data == "promotion:view:5"


def test_session_builder_has_bottom_navigation_row() -> None:
    keyboard = session_builder_keyboard(
        selected_count=1,
        category_nodes=[],
        moves=[],
        category_code=None,
        recent_moves=None,
        recent=False,
    )
    assert keyboard.inline_keyboard[-2][0].text == "➕ Add New Move"
    assert keyboard.inline_keyboard[-1][0].text == "◀️ Back"
    assert keyboard.inline_keyboard[-1][1].text == "🏠 Open Menu"


def test_category_picker_selects_leaf_without_use_this_group() -> None:
    leaf = ArsenalCategory(code="leaf", name="Leaf", parent_code="root", sort_order=1)
    node = CategoryNode(category=leaf, child_count=0, move_count=0)
    keyboard = category_picker_keyboard(
        category_nodes=[node],
        current_code="root",
        open_action="pickcat:open",
        back_action="pickcat:back",
        root_back_callback="arsenal:home",
        select_leaf_action="pickcat:select",
    )
    assert keyboard.inline_keyboard[0][0].callback_data == "pickcat:select:leaf"
    assert keyboard.inline_keyboard[-1][0].callback_data == "pickcat:back:root"


def test_history_keyboard_has_paging_and_navigation() -> None:
    keyboard = history_keyboard(
        [("logged_session:view:1", "✏️ Edit 11 March, 2026")],
        offset=10,
        has_previous=True,
        has_next=True,
        back_callback="menu:me",
    )
    assert keyboard.inline_keyboard[0][0].callback_data == "logged_session:view:1"
    assert keyboard.inline_keyboard[1][0].callback_data == "history:0"
    assert keyboard.inline_keyboard[1][1].callback_data == "history:20"
    assert keyboard.inline_keyboard[-1][0].callback_data == "menu:me"
