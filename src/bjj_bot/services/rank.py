from __future__ import annotations

from dataclasses import dataclass

from bjj_bot.models import Belt


BELT_ORDER = [
    Belt.WHITE.value,
    Belt.BLUE.value,
    Belt.PURPLE.value,
    Belt.BROWN.value,
    Belt.BLACK.value,
]
MAX_STRIPES = 4


class RankError(ValueError):
    pass


@dataclass(slots=True)
class RankState:
    belt: str
    stripes: int


def add_stripe(state: RankState) -> RankState:
    if state.stripes >= MAX_STRIPES:
        raise RankError("Max stripes reached for current belt")
    return RankState(belt=state.belt, stripes=state.stripes + 1)


def promote_belt(state: RankState) -> RankState:
    try:
        index = BELT_ORDER.index(state.belt)
    except ValueError as exc:
        raise RankError("Unknown belt") from exc
    if index >= len(BELT_ORDER) - 1:
        raise RankError("Black belt is terminal in v1")
    return RankState(belt=BELT_ORDER[index + 1], stripes=0)
