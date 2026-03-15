from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CategorySeed:
    code: str
    name: str
    parent_code: str | None
    sort_order: int


# Clean, strictly non-overlapping position-first taxonomy.
# Every technique is filed under the position you initiate it from.
CATEGORY_SEEDS: list[CategorySeed] = [
    # Standing ──────────────────────────────────────────────────────────
    CategorySeed(code="standing",          name="Standing",             parent_code=None,          sort_order=10),
    CategorySeed(code="standing_takedowns",name="Takedowns & Trips",   parent_code="standing",    sort_order=11),
    CategorySeed(code="standing_throws",   name="Throws",              parent_code="standing",    sort_order=12),
    CategorySeed(code="standing_clinch",   name="Clinch & Body Lock",  parent_code="standing",    sort_order=13),

    # Guard (you on bottom) ─────────────────────────────────────────────
    CategorySeed(code="guard",             name="Guard",               parent_code=None,          sort_order=20),
    CategorySeed(code="guard_closed",      name="Closed Guard",        parent_code="guard",       sort_order=21),
    CategorySeed(code="guard_half",        name="Half Guard",          parent_code="guard",       sort_order=22),
    CategorySeed(code="guard_open",        name="Open Guard & Butterfly", parent_code="guard",    sort_order=23),

    # Passing (you on top, breaking/passing the guard) ──────────────────
    CategorySeed(code="passing",           name="Passing",             parent_code=None,          sort_order=30),

    # Top Control (you on top, past the guard) ──────────────────────────
    # Note: DB code kept as top_positions for backward compat with existing rows
    CategorySeed(code="top_positions",     name="Top Control",         parent_code=None,          sort_order=40),
    CategorySeed(code="top_side_control",  name="Side Control",        parent_code="top_positions", sort_order=41),
    CategorySeed(code="top_mount",         name="Mount",               parent_code="top_positions", sort_order=42),
    CategorySeed(code="top_back",          name="Back & Turtle",       parent_code="top_positions", sort_order=43),

    # Escapes (you in a bad spot) ───────────────────────────────────────
    CategorySeed(code="escapes",           name="Defensive Positions",  parent_code=None,          sort_order=50),
    CategorySeed(code="escapes_side",      name="Side Control Bottom", parent_code="escapes",     sort_order=51),
    CategorySeed(code="escapes_mount",     name="Mount Bottom",        parent_code="escapes",     sort_order=52),
    CategorySeed(code="escapes_back",      name="Back & Turtle Bottom",parent_code="escapes",     sort_order=53),

    # Leg Locks (position-ambiguous; their own department) ──────────────
    CategorySeed(code="leg_locks",         name="Leg Locks",           parent_code=None,          sort_order=60),
]

DEFAULT_MOVE_TAGS = (
    "gi",
    "no-gi",
    "competition",
    "drill",
    "fundamental",
    "advanced",
    "left side",
    "right side",
    "submission",
    "control",
    "transition",
    "escape",
    "counter",
    "chain",
)
