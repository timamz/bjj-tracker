"""One-time migration: replace the old overlapping taxonomy with a clean
position-first taxonomy.  All existing moves are preserved.

New taxonomy (strictly non-overlapping, position-first):
  Standing
    Takedowns & Trips
    Throws
    Clinch & Body Lock
  Guard
    Closed Guard
    Half Guard
    Open Guard & Butterfly
  Passing
  Top Control
    Side Control
    Mount
    Back & Turtle
  Escapes
    Side Control Escapes
    Mount Escapes
    Back & Turtle Escapes
  Leg Locks
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "bjj_bot.sqlite3"


def run(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = OFF")

    # ------------------------------------------------------------------
    # 1. Snapshot existing moves (safety check)
    # ------------------------------------------------------------------
    moves_before = con.execute("SELECT id, name, category_code FROM arsenal_moves ORDER BY id").fetchall()
    print(f"Moves before migration: {len(moves_before)}")
    for row in moves_before:
        print(f"  {row[0]:3d}  {row[2]:30s}  {row[1]}")

    # ------------------------------------------------------------------
    # 2. Create new categories that do not yet exist
    # ------------------------------------------------------------------
    new_cats = [
        # code, name, parent_code, sort_order
        ("standing_clinch",  "Clinch & Body Lock",       "standing",      13),
        ("passing",          "Passing",                   None,            30),
        ("top_control",      "Top Control",               None,            40),
        ("escapes_side",     "Side Control Escapes",      "escapes",       51),
        ("escapes_mount",    "Mount Escapes",             "escapes",       52),
        ("escapes_back",     "Back & Turtle Escapes",     "escapes",       53),
        ("leg_locks",        "Leg Locks",                 None,            60),
    ]
    for code, name, parent, order in new_cats:
        existing = con.execute(
            "SELECT code FROM arsenal_categories WHERE code=?", (code,)
        ).fetchone()
        if not existing:
            con.execute(
                "INSERT INTO arsenal_categories (code, name, parent_code, sort_order) VALUES (?,?,?,?)",
                (code, name, parent, order),
            )
            print(f"  Created category: {code} ({name})")

    # ------------------------------------------------------------------
    # 3. Re-home existing moves to new categories
    # ------------------------------------------------------------------
    # old_category_code -> new_category_code
    category_remap = {
        # standing transitions → clinch
        "standing_transitions": "standing_clinch",
        # guard passes / Torreando / guard break → passing
        "transitions_passes": "passing",
        # user-created guard escapes category (6bdeaf2b1e5d) → passing
        # (Technical Stand Up Guard Break is breaking the guard, not escaping)
        "6bdeaf2b1e5d": "passing",
        # user-created "Close Guard Atacks" (881bd7e89e15) → guard_closed
        "881bd7e89e15": "guard_closed",
        # user-created "From Close Guard" (d81df37a4561) → guard_closed
        "d81df37a4561": "guard_closed",
        # user-created "Sind Control Escapes" (cfcc90a30c11) → escapes_side
        "cfcc90a30c11": "escapes_side",
        # user-created "Sequences & Counter-Offense" (737f1d223745) → escapes_side
        "737f1d223745": "escapes_side",
    }
    for old_code, new_code in category_remap.items():
        n = con.execute(
            "UPDATE arsenal_moves SET category_code=? WHERE category_code=?",
            (new_code, old_code),
        ).rowcount
        if n:
            print(f"  Remapped {n} move(s): {old_code} → {new_code}")

    # ------------------------------------------------------------------
    # 4. Rename / clean up existing top-level and sub-categories
    # ------------------------------------------------------------------
    renames = [
        ("standing",       "Standing",               None,   10),
        ("standing_takedowns", "Takedowns & Trips",  "standing", 11),
        ("standing_throws","Throws",                 "standing", 12),
        ("standing_clinch","Clinch & Body Lock",     "standing", 13),
        ("guard",          "Guard",                  None,   20),
        ("guard_closed",   "Closed Guard",           "guard",21),
        ("guard_half",     "Half Guard",             "guard",22),
        ("guard_open",     "Open Guard & Butterfly", "guard",23),
        ("passing",        "Passing",                None,   30),
        ("top_positions",  "Top Control",            None,   40),
        ("top_side_control","Side Control",          "top_positions",41),
        ("top_mount",      "Mount",                  "top_positions",42),
        ("top_back",       "Back & Turtle",          "top_positions",43),
        ("escapes",        "Escapes",                None,   50),
        ("escapes_side",   "Side Control Escapes",   "escapes",51),
        ("escapes_mount",  "Mount Escapes",          "escapes",52),
        ("escapes_back",   "Back & Turtle Escapes",  "escapes",53),
        ("leg_locks",      "Leg Locks",              None,   60),
    ]
    for code, name, parent, order in renames:
        con.execute(
            "UPDATE arsenal_categories SET name=?, parent_code=?, sort_order=? WHERE code=?",
            (name, parent, order, code),
        )

    # ------------------------------------------------------------------
    # 5. Delete every category NOT in the new taxonomy
    # ------------------------------------------------------------------
    keep = {r[0] for r in renames}
    all_cats = con.execute("SELECT code FROM arsenal_categories").fetchall()
    to_delete = [row[0] for row in all_cats if row[0] not in keep]
    for code in to_delete:
        con.execute("DELETE FROM arsenal_categories WHERE code=?", (code,))
    print(f"  Deleted {len(to_delete)} old categories")

    # ------------------------------------------------------------------
    # 6. Verify no moves were lost and all reference valid categories
    # ------------------------------------------------------------------
    moves_after = con.execute("SELECT id, name, category_code FROM arsenal_moves ORDER BY id").fetchall()
    print(f"\nMoves after migration: {len(moves_after)}")
    ok = True
    for row in moves_after:
        cat = con.execute(
            "SELECT name FROM arsenal_categories WHERE code=?", (row[2],)
        ).fetchone()
        cat_name = cat[0] if cat else "!!! MISSING CATEGORY !!!"
        status = "" if cat else " *** ERROR ***"
        print(f"  {row[0]:3d}  {row[2]:20s} ({cat_name:30s})  {row[1]}{status}")
        if not cat:
            ok = False

    if len(moves_before) != len(moves_after):
        print(f"\n!!! MOVE COUNT CHANGED: {len(moves_before)} -> {len(moves_after)} !!!")
        ok = False

    if ok:
        con.commit()
        print("\n✓ Migration committed successfully.")
    else:
        con.rollback()
        print("\n✗ Errors found — rolled back.")
        sys.exit(1)

    con.close()


if __name__ == "__main__":
    run(DB)
