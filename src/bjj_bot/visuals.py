from __future__ import annotations

from dataclasses import dataclass
from html import escape


DEFAULT_BELT_EMOJIS = {
    "white": "⚪",
    "blue": "🔵",
    "purple": "🟣",
    "brown": "🟤",
    "black": "⚫",
}

DEFAULT_STRIPE_EMOJI = "⬜"


@dataclass(frozen=True, slots=True)
class RankVisual:
    sticker_id: str | None
    text: str


def rank_key(belt: str, stripes: int) -> str:
    return f"{belt}:{stripes}"


def belt_emoji_for(belt: str, belt_emoji_map: dict[str, str] | None = None) -> str:
    if belt_emoji_map and belt in belt_emoji_map:
        return belt_emoji_map[belt]
    return DEFAULT_BELT_EMOJIS[belt]


def build_rank_text(
    belt: str,
    stripes: int,
    belt_emoji_map: dict[str, str] | None = None,
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> str:
    belt_block = belt_emoji_for(belt, belt_emoji_map)
    key = rank_key(belt, stripes)
    if rank_custom_emoji_map and key in rank_custom_emoji_map:
        return f'<tg-emoji emoji-id="{escape(rank_custom_emoji_map[key])}">{escape(belt_block)}</tg-emoji>'
    belt_block = belt_emoji_for(belt, belt_emoji_map)
    if stripes <= 0:
        return belt_block
    stripes_block = DEFAULT_STRIPE_EMOJI * stripes
    return f"{belt_block} {stripes_block}"


def get_rank_visual(
    belt: str,
    stripes: int,
    sticker_map: dict[str, str],
    belt_emoji_map: dict[str, str] | None = None,
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> RankVisual:
    key = rank_key(belt, stripes)
    sticker_id = None if rank_custom_emoji_map and key in rank_custom_emoji_map else sticker_map.get(key)
    return RankVisual(
        sticker_id=sticker_id,
        text=build_rank_text(belt, stripes, belt_emoji_map, rank_custom_emoji_map),
    )
