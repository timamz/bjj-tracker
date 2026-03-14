from datetime import date

from bjj_bot.handlers.menu import _format_duration


def test_duration_uses_plural_zero_values() -> None:
    assert _format_duration(date(2026, 3, 14), date(2026, 3, 14)) == "0 years, 0 months, 0 days"


def test_duration_uses_singular_labels_for_one() -> None:
    assert _format_duration(date(2025, 2, 13), date(2026, 3, 14)) == "1 year, 1 month, 1 day"


def test_duration_mixes_singular_and_plural_labels() -> None:
    assert _format_duration(date(2024, 2, 14), date(2026, 3, 15)) == "2 years, 1 month, 1 day"
