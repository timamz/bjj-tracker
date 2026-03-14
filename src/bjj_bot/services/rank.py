from __future__ import annotations

from dataclasses import dataclass

from bjj_bot.models import Belt


BELT_ORDER = [
    Belt.WHITE.value,
    Belt.BLUE.value,
    Belt.PURPLE.value,
    Belt.BROWN.value,
    Belt.BLACK.value,
    Belt.CORAL.value,
    Belt.RED_WHITE.value,
    Belt.RED.value,
]

MAX_STRIPES: dict[str, int] = {
    Belt.WHITE.value: 4,
    Belt.BLUE.value: 4,
    Belt.PURPLE.value: 4,
    Belt.BROWN.value: 4,
    Belt.BLACK.value: 6,
    Belt.CORAL.value: 0,
    Belt.RED_WHITE.value: 0,
    Belt.RED.value: 0,
}


class RankError(ValueError):
    pass


@dataclass(slots=True)
class RankState:
    belt: str
    stripes: int


def max_stripes_for(belt: str) -> int:
    return MAX_STRIPES.get(belt, 4)


def add_stripe(state: RankState) -> RankState:
    limit = max_stripes_for(state.belt)
    if state.stripes >= limit:
        raise RankError("Max stripes reached for current belt")
    return RankState(belt=state.belt, stripes=state.stripes + 1)


def promote_belt(state: RankState) -> RankState:
    try:
        index = BELT_ORDER.index(state.belt)
    except ValueError as exc:
        raise RankError("Unknown belt") from exc
    if index >= len(BELT_ORDER) - 1:
        raise RankError("Already at the highest belt")
    return RankState(belt=BELT_ORDER[index + 1], stripes=0)


def all_rank_states() -> list[RankState]:
    states: list[RankState] = []
    for belt in BELT_ORDER:
        for stripes in range(max_stripes_for(belt) + 1):
            states.append(RankState(belt=belt, stripes=stripes))
    return states


def rank_position(state: RankState) -> int:
    try:
        belt_index = BELT_ORDER.index(state.belt)
    except ValueError as exc:
        raise RankError("Unknown belt") from exc
    limit = max_stripes_for(state.belt)
    if state.stripes < 0 or state.stripes > limit:
        raise RankError("Unknown stripe count")
    pos = 0
    for i in range(belt_index):
        pos += max_stripes_for(BELT_ORDER[i]) + 1
    return pos + state.stripes


def next_rank_choices(state: RankState) -> list[RankState]:
    current_position = rank_position(state)
    return [candidate for candidate in all_rank_states() if rank_position(candidate) > current_position]


def set_rank(current: RankState, target: RankState) -> RankState:
    if rank_position(target) <= rank_position(current):
        raise RankError("Pick a higher rank")
    return target
