from bjj_bot.handlers.menu import _preferred_session_add_move_category


def test_prefers_current_session_category() -> None:
    assert _preferred_session_add_move_category(
        {"current_session_category": "transitions_passes", "last_session_category": "guard_closed"}
    ) == "transitions_passes"


def test_falls_back_to_last_session_category() -> None:
    assert _preferred_session_add_move_category(
        {"current_session_category": None, "last_session_category": "guard_closed"}
    ) == "guard_closed"


def test_returns_none_without_category_history() -> None:
    assert _preferred_session_add_move_category({}) is None
