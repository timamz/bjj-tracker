from datetime import date

from bjj_bot.handlers.menu import _parse_user_date, _short_date
from bjj_bot.keyboards import format_quick_date_label


def test_short_date_uses_dd_mm_yyyy() -> None:
    assert _short_date(date(2026, 3, 13)) == "13-03-2026"


def test_parse_user_date_uses_dd_mm_yyyy() -> None:
    assert _parse_user_date("13-03-2026") == date(2026, 3, 13)


def test_quick_date_label_uses_weekday_day_month() -> None:
    assert format_quick_date_label(date(2026, 3, 16)) == "Monday, 16 March"
