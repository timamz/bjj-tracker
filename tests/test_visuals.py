from bjj_bot.visuals import build_rank_text, get_rank_visual


def test_build_rank_text_uses_belt_color_and_stripes() -> None:
    assert build_rank_text("white", 0) == "⚪"
    assert build_rank_text("blue", 2) == "🔵 ⬜⬜"
    assert build_rank_text("black", 4) == "⚫ ⬜⬜⬜⬜"


def test_build_rank_text_uses_custom_belt_emojis() -> None:
    belt_emojis = {"purple": "🟪"}
    assert build_rank_text("purple", 1, belt_emojis) == "🟪 ⬜"


def test_build_rank_text_prefers_rank_custom_emoji() -> None:
    rank_custom_emojis = {"blue:2": "1234567890"}
    assert build_rank_text("blue", 2, None, rank_custom_emojis) == '<tg-emoji emoji-id="1234567890">🔵</tg-emoji>'


def test_get_rank_visual_skips_sticker_when_rank_custom_emoji_exists() -> None:
    visual = get_rank_visual(
        "brown",
        3,
        {"brown:3": "sticker-file-id"},
        None,
        {"brown:3": "custom-emoji-id"},
    )
    assert visual.sticker_id is None
    assert visual.text == '<tg-emoji emoji-id="custom-emoji-id">🟤</tg-emoji>'
