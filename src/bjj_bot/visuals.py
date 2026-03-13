from __future__ import annotations

from dataclasses import dataclass


BELT_EMOJIS = {
    "white": "⬜",
    "blue": "🟦",
    "purple": "🟪",
    "brown": "🟫",
    "black": "⬛",
}


@dataclass(frozen=True, slots=True)
class RankVisual:
    sticker_id: str | None
    text: str


def rank_key(belt: str, stripes: int) -> str:
    return f"{belt}:{stripes}"


def build_rank_text(belt: str, stripes: int) -> str:
    belt_block = BELT_EMOJIS[belt] * 3
    stripes_block = "⚪" * stripes if stripes else "·"
    return f"{belt_block} {stripes_block}"


def get_rank_visual(belt: str, stripes: int, sticker_map: dict[str, str]) -> RankVisual:
    key = rank_key(belt, stripes)
    return RankVisual(sticker_id=sticker_map.get(key), text=build_rank_text(belt, stripes))

