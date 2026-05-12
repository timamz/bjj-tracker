"""Agent-facing CLI for the BJJ tracker.

This wraps the same service layer the Telegram bot uses, exposing it as a
synchronous command-line tool with JSON output. It does not start the bot.

Run `python -m bjj_bot.cli --help` (or `bjj-cli --help` after install) for usage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bjj_bot.db import init_db
from bjj_bot.models import ArsenalCategory, ArsenalMove, AthleteProgress, Belt, User
from bjj_bot.services import admin as admin_service
from bjj_bot.services import arsenal as arsenal_service
from bjj_bot.services import history as history_service
from bjj_bot.services import promotions as promotion_service
from bjj_bot.services import sessions as session_service
from bjj_bot.services import users as user_service
from bjj_bot.services.rank import RankError


DEFAULT_DB_PATH = Path("/data/bjj_bot.sqlite3")


class CliError(Exception):
    """Raised when the CLI cannot complete a request (bad input, missing row, etc.)."""


def _utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _parse_date(value: str | None) -> date:
    if value is None or value.lower() == "today":
        return date.today()
    if value.lower() == "yesterday":
        return date.today().fromordinal(date.today().toordinal() - 1)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CliError(f"Invalid date '{value}'. Expected YYYY-MM-DD, 'today', or 'yesterday'.") from exc


def _resolve_db_path(args: argparse.Namespace) -> Path:
    raw = args.db or os.environ.get("BJJ_DB_PATH") or os.environ.get("DB_PATH")
    if raw:
        return Path(raw).expanduser()
    # Fallback: project-local data/bjj_bot.sqlite3 if present, else /data.
    project_db = Path(__file__).resolve().parents[2] / "data" / "bjj_bot.sqlite3"
    if project_db.exists():
        return project_db
    return DEFAULT_DB_PATH


async def _resolve_user(session: AsyncSession, telegram_id: int | None) -> User:
    if telegram_id is None:
        owner = os.environ.get("OWNER_ID") or os.environ.get("BJJ_OWNER_ID")
        if owner:
            telegram_id = int(owner)
    if telegram_id is None:
        # If exactly one human user exists, use them.
        users = list(
            (await session.execute(select(User).order_by(User.id))).scalars()
        )
        if len(users) == 1:
            return users[0]
        raise CliError(
            "No user selected. Pass --telegram-id, set OWNER_ID in the env, "
            "or initialize a user via the bot first."
        )
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise CliError(
            f"No user with telegram_id={telegram_id}. The user must /start the bot once "
            "before the CLI can act on their behalf."
        )
    return user


def _move_payload(move: ArsenalMove, category_name: str | None = None) -> dict[str, Any]:
    return {
        "id": move.id,
        "name": move.name,
        "category_code": move.category_code,
        "category_name": category_name,
        "note": move.note or "",
        "tags": sorted(tag.value for tag in move.tags) if move.tags else [],
        "updated_at": _utc_iso(move.updated_at),
    }


def _category_payload(category: ArsenalCategory) -> dict[str, Any]:
    return {
        "code": category.code,
        "name": category.name,
        "parent_code": category.parent_code,
        "sort_order": category.sort_order,
    }


def _progress_payload(progress: AthleteProgress) -> dict[str, Any]:
    return {
        "belt": progress.belt,
        "stripes": progress.stripes,
        "total_sessions": progress.total_sessions,
        "competitor": bool(progress.competitor),
        "last_updated_at": _utc_iso(progress.last_updated_at),
    }


async def _category_name_map(session: AsyncSession) -> dict[str, str]:
    rows = await session.execute(select(ArsenalCategory.code, ArsenalCategory.name))
    return {code: name for code, name in rows.all()}


async def _resolve_move_ids(
    session: AsyncSession,
    *,
    user_id: int,
    explicit_ids: Iterable[int],
    names: Iterable[str],
    fuzzy: bool,
) -> tuple[list[int], list[dict[str, Any]]]:
    resolved: list[int] = list(explicit_ids)
    resolutions: list[dict[str, Any]] = [{"input_id": mid, "matched_id": mid} for mid in resolved]
    for name in names:
        matches = await arsenal_service.search_moves(session, user_id, name, limit=3)
        if not matches:
            raise CliError(
                f"No move found matching '{name}'. List moves with `move list` or create it first."
            )
        chosen = matches[0]
        if not fuzzy and chosen.name.lower() != name.lower():
            raise CliError(
                f"No exact-name match for '{name}'. Closest is '{chosen.name}' (id={chosen.id}); "
                "pass --fuzzy-names to accept fuzzy matches."
            )
        resolved.append(chosen.id)
        resolutions.append(
            {
                "input_name": name,
                "matched_id": chosen.id,
                "matched_name": chosen.name,
                "alternates": [
                    {"id": m.id, "name": m.name} for m in matches[1:]
                ],
            }
        )
    seen: set[int] = set()
    unique_ids: list[int] = []
    for mid in resolved:
        if mid not in seen:
            seen.add(mid)
            unique_ids.append(mid)
    return unique_ids, resolutions


def _emit(args: argparse.Namespace, payload: Any) -> None:
    if getattr(args, "json", False):
        json.dump(payload, sys.stdout, ensure_ascii=False, default=str, indent=2)
        sys.stdout.write("\n")
        return
    if isinstance(payload, dict) and "ok" in payload and len(payload) == 1:
        print("ok")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (list, dict)):
                print(f"{key}:")
                print(json.dumps(value, ensure_ascii=False, default=str, indent=2))
            else:
                print(f"{key}: {value}")
        return
    if isinstance(payload, list):
        for entry in payload:
            print(json.dumps(entry, ensure_ascii=False, default=str))
        return
    print(payload)


# ── command handlers ────────────────────────────────────────────────────────


async def cmd_status(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    progress = await session.scalar(select(AthleteProgress).where(AthleteProgress.user_id == user.id))
    if progress is None:
        raise CliError("Progress row missing — initialise via the bot or `user init`.")
    move_count = await arsenal_service.count_total_moves(session, user.id)
    first = await session_service.first_session_date(session, user_id=user.id)
    total_minutes = await session_service.sum_duration_minutes(session, user_id=user.id)
    return {
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
        },
        "progress": _progress_payload(progress),
        "arsenal_move_count": move_count,
        "first_session_date": first.isoformat() if first else None,
        "total_duration_minutes": total_minutes,
    }


async def cmd_session_log(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    session_date = _parse_date(args.date)
    move_ids, resolutions = await _resolve_move_ids(
        session,
        user_id=user.id,
        explicit_ids=args.move_id or [],
        names=args.move_name or [],
        fuzzy=args.fuzzy_names,
    )
    try:
        training_session = await session_service.log_session(
            session,
            user_id=user.id,
            session_date=session_date,
            move_ids=move_ids,
            duration_minutes=args.duration,
        )
    except session_service.SessionError as exc:
        raise CliError(str(exc)) from exc
    return {
        "session": {
            "id": training_session.id,
            "session_date": training_session.session_date.isoformat(),
            "duration_minutes": training_session.duration_minutes,
            "move_ids": move_ids,
        },
        "resolved_moves": resolutions,
    }


async def cmd_session_list(args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    user = await _resolve_user(session, args.telegram_id)
    items = await history_service.get_session_history(
        session, user_id=user.id, offset=args.offset, limit=args.limit
    )
    return [
        {
            "id": item.entity_id,
            "date": item.date.isoformat(),
            "created_at": _utc_iso(item.created_at),
            "summary": item.text,
        }
        for item in items
    ]


async def cmd_session_show(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    ts = await session_service.get_session(session, user_id=user.id, session_id=args.id)
    if ts is None:
        raise CliError(f"No session with id={args.id} for this user.")
    move_ids = await session_service.get_session_move_ids(
        session, user_id=user.id, session_id=ts.id
    )
    return {
        "id": ts.id,
        "session_date": ts.session_date.isoformat(),
        "duration_minutes": ts.duration_minutes,
        "created_at": _utc_iso(ts.created_at),
        "move_ids": move_ids,
    }


async def cmd_session_update(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    move_ids: list[int] | None = None
    resolutions: list[dict[str, Any]] | None = None
    if args.move_id is not None or args.move_name:
        ids, resolutions = await _resolve_move_ids(
            session,
            user_id=user.id,
            explicit_ids=args.move_id or [],
            names=args.move_name or [],
            fuzzy=args.fuzzy_names,
        )
        move_ids = ids
    session_date = _parse_date(args.date) if args.date else None
    try:
        updated = await session_service.update_session(
            session,
            user_id=user.id,
            session_id=args.id,
            session_date=session_date,
            move_ids=move_ids,
            duration_minutes=args.duration,
            clear_duration=args.clear_duration,
        )
    except session_service.SessionError as exc:
        raise CliError(str(exc)) from exc
    if updated is None:
        raise CliError(f"No session with id={args.id} for this user.")
    return {
        "id": updated.id,
        "session_date": updated.session_date.isoformat(),
        "duration_minutes": updated.duration_minutes,
        "resolved_moves": resolutions,
    }


async def cmd_session_delete(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    ok = await session_service.delete_session(session, user_id=user.id, session_id=args.id)
    if not ok:
        raise CliError(f"No session with id={args.id} for this user.")
    return {"ok": True, "deleted_id": args.id}


async def cmd_history(args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    user = await _resolve_user(session, args.telegram_id)
    items = await history_service.get_history(
        session, user_id=user.id, offset=args.offset, limit=args.limit
    )
    return [
        {
            "kind": item.kind,
            "id": item.entity_id,
            "date": item.date.isoformat(),
            "created_at": _utc_iso(item.created_at),
            "summary": item.text,
        }
        for item in items
    ]


async def cmd_move_list(args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    user = await _resolve_user(session, args.telegram_id)
    category_names = await _category_name_map(session)
    if args.category:
        moves = await arsenal_service.list_moves_in_category(session, user.id, args.category)
    elif args.recent:
        moves = await arsenal_service.list_recent_moves(session, user.id, limit=args.limit)
    else:
        # All moves for the user.
        rows = await session.execute(
            select(ArsenalMove).where(ArsenalMove.user_id == user.id).order_by(ArsenalMove.name)
        )
        moves = list(rows.scalars())
        # Refresh tag relationships.
        for move in moves:
            await session.refresh(move, attribute_names=["tags"])
    return [_move_payload(m, category_names.get(m.category_code)) for m in moves]


async def cmd_move_search(args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    user = await _resolve_user(session, args.telegram_id)
    category_names = await _category_name_map(session)
    moves = await arsenal_service.search_moves(session, user.id, args.query, limit=args.limit)
    return [_move_payload(m, category_names.get(m.category_code)) for m in moves]


async def cmd_move_show(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    move = await arsenal_service.get_move(session, user.id, args.id)
    if move is None:
        raise CliError(f"No move with id={args.id} for this user.")
    category_names = await _category_name_map(session)
    counts = await arsenal_service.get_move_session_counts(session, [move.id])
    payload = _move_payload(move, category_names.get(move.category_code))
    payload["practiced_count"] = counts.get(move.id, 0)
    return payload


async def cmd_move_add(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    category = await arsenal_service.get_category(session, args.category)
    if category is None:
        raise CliError(
            f"Unknown category code '{args.category}'. List categories with `category list`."
        )
    tags = arsenal_service.normalize_tags(args.tags)
    move = await arsenal_service.create_move(
        session,
        user_id=user.id,
        name=args.name,
        category_code=args.category,
        note=args.note or "",
        tags=tags,
    )
    return _move_payload(move, category.name)


async def cmd_move_update(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    if args.category is not None:
        category = await arsenal_service.get_category(session, args.category)
        if category is None:
            raise CliError(f"Unknown category code '{args.category}'.")
    tags = arsenal_service.normalize_tags(args.tags) if args.tags is not None else None
    move = await arsenal_service.update_move(
        session,
        user_id=user.id,
        move_id=args.id,
        name=args.name,
        category_code=args.category,
        note=args.note,
        tags=tags,
    )
    if move is None:
        raise CliError(f"No move with id={args.id} for this user.")
    category_names = await _category_name_map(session)
    return _move_payload(move, category_names.get(move.category_code))


async def cmd_move_delete(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    ok = await arsenal_service.delete_move(session, user_id=user.id, move_id=args.id)
    if not ok:
        raise CliError(f"No move with id={args.id} for this user.")
    return {"ok": True, "deleted_id": args.id}


async def cmd_category_list(args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    user = await _resolve_user(session, args.telegram_id)
    nodes = await arsenal_service.list_child_categories(
        session, args.parent, user_id=user.id
    )
    return [
        {
            **_category_payload(node.category),
            "child_count": node.child_count,
            "move_count": node.move_count,
        }
        for node in nodes
    ]


async def cmd_promotion_list(args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    user = await _resolve_user(session, args.telegram_id)
    promotions = await promotion_service.list_promotions(
        session, user_id=user.id, offset=args.offset, limit=args.limit
    )
    return [
        {
            "id": p.id,
            "promotion_date": p.promotion_date.isoformat(),
            "belt": p.belt,
            "stripes": p.stripes,
            "session_number": p.session_number,
            "created_at": _utc_iso(p.created_at),
        }
        for p in promotions
    ]


async def cmd_promotion_apply(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    promo_date = _parse_date(args.date)
    try:
        if args.belt is not None or args.stripes is not None:
            if args.belt is None or args.stripes is None:
                raise CliError("Provide both --belt and --stripes when setting an explicit rank.")
            promotion = await promotion_service.set_promotion_rank(
                session,
                user_id=user.id,
                promotion_date=promo_date,
                belt=args.belt,
                stripes=args.stripes,
            )
        else:
            promotion = await promotion_service.apply_promotion(
                session, user_id=user.id, promotion_date=promo_date, kind=args.kind
            )
    except RankError as exc:
        raise CliError(str(exc)) from exc
    return {
        "id": promotion.id,
        "promotion_date": promotion.promotion_date.isoformat(),
        "belt": promotion.belt,
        "stripes": promotion.stripes,
        "session_number": promotion.session_number,
    }


async def cmd_promotion_delete(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    ok = await promotion_service.delete_promotion(
        session, user_id=user.id, promotion_id=args.id
    )
    if not ok:
        raise CliError(f"No promotion with id={args.id} for this user.")
    return {"ok": True, "deleted_id": args.id}


async def cmd_user_init(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    telegram_id = args.init_telegram_id if args.init_telegram_id is not None else args.telegram_id
    if telegram_id is None:
        raise CliError("Pass --telegram-id (top-level or --init-telegram-id) to identify the user.")
    existing = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if existing is not None:
        progress = await user_service.get_progress(session, existing.id)
        return {
            "id": existing.id,
            "telegram_id": existing.telegram_id,
            "username": existing.username,
            "first_name": existing.first_name,
            "last_name": existing.last_name,
            "progress": _progress_payload(progress),
            "created": False,
        }
    user = User(
        telegram_id=telegram_id,
        username=args.username,
        first_name=args.first_name,
        last_name=args.last_name,
    )
    session.add(user)
    await session.flush()
    session.add(
        AthleteProgress(user_id=user.id, belt=Belt.WHITE.value, stripes=0, total_sessions=0)
    )
    await session.commit()
    await session.refresh(user)
    progress = await user_service.get_progress(session, user.id)
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "progress": _progress_payload(progress),
        "created": True,
    }


async def cmd_user_list(_args: argparse.Namespace, session: AsyncSession) -> list[dict[str, Any]]:
    rows = await session.execute(select(User).order_by(User.id))
    payload: list[dict[str, Any]] = []
    for user in rows.scalars():
        progress = await session.scalar(
            select(AthleteProgress).where(AthleteProgress.user_id == user.id)
        )
        payload.append(
            {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "created_at": _utc_iso(user.created_at),
                "progress": _progress_payload(progress) if progress else None,
            }
        )
    return payload


async def cmd_user_set_competitor(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    if args.on == args.off:
        raise CliError("Pass exactly one of --on or --off.")
    progress = await user_service.set_competitor(session, user.id, args.on)
    return {"competitor": bool(progress.competitor), "user_id": user.id}


async def cmd_category_create(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    parent_code = args.parent
    if parent_code is not None:
        parent = await arsenal_service.get_category(session, parent_code)
        if parent is None:
            raise CliError(f"Unknown parent category '{parent_code}'.")
    category = await arsenal_service.create_category(
        session, name=args.name, parent_code=parent_code
    )
    return _category_payload(category)


async def cmd_category_rename(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    existing = await arsenal_service.get_category(session, args.code)
    if existing is None:
        raise CliError(f"No category with code '{args.code}'.")
    ok = await arsenal_service.rename_category(session, args.code, args.name)
    if not ok:
        raise CliError(f"Failed to rename category '{args.code}'.")
    refreshed = await arsenal_service.get_category(session, args.code)
    return _category_payload(refreshed)  # type: ignore[arg-type]


async def cmd_category_delete(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    existing = await arsenal_service.get_category(session, args.code)
    if existing is None:
        raise CliError(f"No category with code '{args.code}'.")
    if not args.confirm:
        raise CliError(
            f"Deleting '{args.code}' will cascade to all sub-groups and their moves. "
            "Pass --confirm to proceed."
        )
    await arsenal_service.delete_category(session, args.code)
    return {"ok": True, "deleted_code": args.code}


async def cmd_category_show(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    category = await arsenal_service.get_category(session, args.code)
    if category is None:
        raise CliError(f"No category with code '{args.code}'.")
    path = await arsenal_service.get_category_path(session, args.code)
    user = await _resolve_user(session, args.telegram_id)
    children = await arsenal_service.list_child_categories(
        session, args.code, user_id=user.id
    )
    return {
        **_category_payload(category),
        "path": [_category_payload(c) for c in path],
        "children": [
            {
                **_category_payload(node.category),
                "child_count": node.child_count,
                "move_count": node.move_count,
            }
            for node in children
        ],
    }


async def cmd_promotion_update(args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    user = await _resolve_user(session, args.telegram_id)
    promotion_date = _parse_date(args.date) if args.date else None
    try:
        promotion = await promotion_service.update_promotion(
            session,
            user_id=user.id,
            promotion_id=args.id,
            promotion_date=promotion_date,
            belt=args.belt,
            stripes=args.stripes,
        )
    except RankError as exc:
        raise CliError(str(exc)) from exc
    if promotion is None:
        raise CliError(f"No promotion with id={args.id} for this user.")
    return {
        "id": promotion.id,
        "promotion_date": promotion.promotion_date.isoformat(),
        "belt": promotion.belt,
        "stripes": promotion.stripes,
        "session_number": promotion.session_number,
    }


async def cmd_admin_stats(_args: argparse.Namespace, session: AsyncSession) -> dict[str, Any]:
    stats = await admin_service.get_admin_stats(session)
    return {
        "total_users": stats.total_users,
        "new_users_week": stats.new_users_week,
        "new_users_month": stats.new_users_month,
        "active_users_30d": stats.active_users_30d,
        "total_sessions": stats.total_sessions,
        "total_moves": stats.total_moves,
    }


def cmd_schema(_args: argparse.Namespace) -> dict[str, Any]:
    """Static schema docs that an agent can read to understand the data model."""
    return {
        "entities": {
            "user": "Telegram-keyed account. CLI selects via --telegram-id or $OWNER_ID.",
            "progress": "Current belt, stripes, total_sessions, competitor flag.",
            "training_session": (
                "Date-stamped class. Fields: session_date (YYYY-MM-DD), "
                "duration_minutes (int, optional), zero or more practiced moves."
            ),
            "arsenal_move": (
                "User-owned technique. Fields: name, category_code, note (free text), tags. "
                "Sessions reference moves by id."
            ),
            "promotion": "Belt/stripes change on a date. Snapshots session_number.",
            "arsenal_category": "Position-first taxonomy tree (e.g. guard, guard_closed).",
        },
        "belts": [b.value for b in Belt],
        "notes": [
            "Sessions have NO free-text notes column. Encode 'felt tired' style remarks "
            "outside the tracker, or add them as the note on a move you practiced.",
            "Move names are matched fuzzily; pass --fuzzy-names to accept the best match.",
            "Default user comes from $OWNER_ID; otherwise pass --telegram-id explicitly.",
        ],
    }


# ── argument parser ─────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bjj-cli",
        description=(
            "Agent-facing CLI for the BJJ tracker. Wraps the same service layer as the "
            "Telegram bot. Outputs human-readable text by default; pass --json for "
            "structured output suitable for programmatic consumers."
        ),
    )
    parser.add_argument("--db", help="Path to bjj_bot.sqlite3 (defaults to $BJJ_DB_PATH / $DB_PATH / project data dir).")
    parser.add_argument(
        "--telegram-id",
        type=int,
        help="Telegram user id to operate on. Defaults to $OWNER_ID, then the sole user if only one exists.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text.")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show current belt, stripes, totals.").set_defaults(handler=cmd_status)

    sub.add_parser("schema", help="Print data-model summary for agents.").set_defaults(handler=cmd_schema)

    # session group
    s_session = sub.add_parser("session", help="Training-session commands.").add_subparsers(dest="action", required=True)

    p_log = s_session.add_parser("log", help="Log a training session.")
    p_log.add_argument("--date", help="YYYY-MM-DD, 'today', or 'yesterday' (default: today).")
    p_log.add_argument("--duration", type=int, help="Duration in minutes.")
    p_log.add_argument("--move-id", type=int, action="append", help="Move id (repeatable).")
    p_log.add_argument("--move-name", action="append", help="Move name to look up (repeatable).")
    p_log.add_argument("--fuzzy-names", action="store_true", help="Accept best fuzzy match for --move-name.")
    p_log.set_defaults(handler=cmd_session_log)

    p_list = s_session.add_parser("list", help="List recent sessions.")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--offset", type=int, default=0)
    p_list.set_defaults(handler=cmd_session_list)

    p_show = s_session.add_parser("show", help="Show a single session.")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(handler=cmd_session_show)

    p_upd = s_session.add_parser("update", help="Update an existing session.")
    p_upd.add_argument("id", type=int)
    p_upd.add_argument("--date")
    p_upd.add_argument("--duration", type=int)
    p_upd.add_argument("--clear-duration", action="store_true")
    p_upd.add_argument("--move-id", type=int, action="append", help="Replace move list (repeatable).")
    p_upd.add_argument("--move-name", action="append", help="Move name to look up (repeatable).")
    p_upd.add_argument("--fuzzy-names", action="store_true")
    p_upd.set_defaults(handler=cmd_session_update)

    p_del = s_session.add_parser("delete", help="Delete a session.")
    p_del.add_argument("id", type=int)
    p_del.set_defaults(handler=cmd_session_delete)

    p_hist = sub.add_parser("history", help="Combined session + promotion timeline.")
    p_hist.add_argument("--limit", type=int, default=10)
    p_hist.add_argument("--offset", type=int, default=0)
    p_hist.set_defaults(handler=cmd_history)

    # move group
    s_move = sub.add_parser("move", help="Arsenal-move commands.").add_subparsers(dest="action", required=True)

    p_mlist = s_move.add_parser("list", help="List moves (all, recent, or by category).")
    p_mlist.add_argument("--category", help="Category code to filter by.")
    p_mlist.add_argument("--recent", action="store_true", help="Limit to most recently updated.")
    p_mlist.add_argument("--limit", type=int, default=20)
    p_mlist.set_defaults(handler=cmd_move_list)

    p_msearch = s_move.add_parser("search", help="Fuzzy-search the arsenal.")
    p_msearch.add_argument("query")
    p_msearch.add_argument("--limit", type=int, default=12)
    p_msearch.set_defaults(handler=cmd_move_search)

    p_mshow = s_move.add_parser("show", help="Show one move with practice count.")
    p_mshow.add_argument("id", type=int)
    p_mshow.set_defaults(handler=cmd_move_show)

    p_madd = s_move.add_parser("add", help="Create a new arsenal move.")
    p_madd.add_argument("--name", required=True)
    p_madd.add_argument("--category", required=True, help="Category code (see `category list`).")
    p_madd.add_argument("--note", default="")
    p_madd.add_argument("--tags", help="Comma-separated tags.")
    p_madd.set_defaults(handler=cmd_move_add)

    p_mupd = s_move.add_parser("update", help="Update fields on an existing move.")
    p_mupd.add_argument("id", type=int)
    p_mupd.add_argument("--name")
    p_mupd.add_argument("--category")
    p_mupd.add_argument("--note")
    p_mupd.add_argument("--tags", help="Comma-separated tags (replaces existing).")
    p_mupd.set_defaults(handler=cmd_move_update)

    p_mdel = s_move.add_parser("delete", help="Delete a move (also removes session links).")
    p_mdel.add_argument("id", type=int)
    p_mdel.set_defaults(handler=cmd_move_delete)

    # category group
    s_cat = sub.add_parser(
        "category",
        help="Arsenal taxonomy (a.k.a. groups). Seeded categories + user-created groups.",
    ).add_subparsers(dest="action", required=True)
    p_clist = s_cat.add_parser("list", help="List child categories under a parent code (omit for roots).")
    p_clist.add_argument("--parent", default=None)
    p_clist.set_defaults(handler=cmd_category_list)

    p_cshow = s_cat.add_parser("show", help="Show one category with path and children.")
    p_cshow.add_argument("code")
    p_cshow.set_defaults(handler=cmd_category_show)

    p_ccreate = s_cat.add_parser(
        "create",
        help="Create a new group under --parent (omit for a root). Code is auto-generated.",
    )
    p_ccreate.add_argument("--name", required=True)
    p_ccreate.add_argument("--parent", default=None, help="Parent category code; omit for top-level.")
    p_ccreate.set_defaults(handler=cmd_category_create)

    p_crename = s_cat.add_parser("rename", help="Rename an existing category.")
    p_crename.add_argument("code")
    p_crename.add_argument("--name", required=True)
    p_crename.set_defaults(handler=cmd_category_rename)

    p_cdel = s_cat.add_parser(
        "delete",
        help="Delete a category and all descendant groups + moves. Requires --confirm.",
    )
    p_cdel.add_argument("code")
    p_cdel.add_argument("--confirm", action="store_true", help="Acknowledge cascading delete.")
    p_cdel.set_defaults(handler=cmd_category_delete)

    # promotion group
    s_promo = sub.add_parser("promotion", help="Belt-progression commands.").add_subparsers(dest="action", required=True)
    p_plist = s_promo.add_parser("list", help="List recorded promotions.")
    p_plist.add_argument("--limit", type=int, default=10)
    p_plist.add_argument("--offset", type=int, default=0)
    p_plist.set_defaults(handler=cmd_promotion_list)

    p_papply = s_promo.add_parser("apply", help="Record a promotion (stripe, belt, or explicit rank).")
    p_papply.add_argument("--kind", choices=("stripe", "belt"), default="stripe")
    p_papply.add_argument("--date", help="Promotion date (default: today).")
    p_papply.add_argument("--belt", help="Set explicit rank: belt name (e.g. blue).")
    p_papply.add_argument("--stripes", type=int, help="Set explicit rank: stripe count.")
    p_papply.set_defaults(handler=cmd_promotion_apply)

    p_pupd = s_promo.add_parser("update", help="Edit an existing promotion's date and/or rank.")
    p_pupd.add_argument("id", type=int)
    p_pupd.add_argument("--date", help="New promotion date.")
    p_pupd.add_argument("--belt", help="New belt name.")
    p_pupd.add_argument("--stripes", type=int, help="New stripe count.")
    p_pupd.set_defaults(handler=cmd_promotion_update)

    p_pdel = s_promo.add_parser("delete", help="Delete a promotion.")
    p_pdel.add_argument("id", type=int)
    p_pdel.set_defaults(handler=cmd_promotion_delete)

    # user group
    s_user = sub.add_parser("user", help="User-account commands.").add_subparsers(dest="action", required=True)

    p_uinit = s_user.add_parser(
        "init",
        help="Create a User+progress row for a telegram id (idempotent). Mirrors /start in the bot.",
    )
    p_uinit.add_argument("--init-telegram-id", type=int, help="Telegram id to create (overrides top-level).")
    p_uinit.add_argument("--username")
    p_uinit.add_argument("--first-name")
    p_uinit.add_argument("--last-name")
    p_uinit.set_defaults(handler=cmd_user_init)

    p_ulist = s_user.add_parser("list", help="List all users in the DB.")
    p_ulist.set_defaults(handler=cmd_user_list)

    p_ucomp = s_user.add_parser(
        "set-competitor",
        help="Set the competitor flag on the user's progress (toggle in the Me view).",
    )
    g = p_ucomp.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true", help="Mark user as competitor.")
    g.add_argument("--off", action="store_true", help="Clear competitor flag.")
    p_ucomp.set_defaults(handler=cmd_user_set_competitor)

    # admin group
    s_admin = sub.add_parser("admin", help="Admin/owner-only insights (mirrors /admin in bot).").add_subparsers(
        dest="action", required=True
    )
    p_astats = s_admin.add_parser("stats", help="Aggregate user/session/move counts.")
    p_astats.set_defaults(handler=cmd_admin_stats)

    return parser


# ── async runner ────────────────────────────────────────────────────────────

AsyncHandler = Callable[[argparse.Namespace, AsyncSession], Awaitable[Any]]
SyncHandler = Callable[[argparse.Namespace], Any]


async def _run(args: argparse.Namespace) -> Any:
    handler = args.handler
    # schema is sync; no DB needed.
    if handler is cmd_schema:
        return handler(args)

    db_path = _resolve_db_path(args)
    if not db_path.exists() and handler is not cmd_user_init:
        raise CliError(
            f"Database not found at {db_path}. Set --db or BJJ_DB_PATH to an existing SQLite file. "
            "Use `user init` to create a fresh DB."
        )
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        await init_db(engine, db_path)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            return await handler(args, session)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except CliError as exc:
        if getattr(args, "json", False):
            json.dump({"error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    _emit(args, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
