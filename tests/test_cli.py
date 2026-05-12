from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bjj_bot import cli
from bjj_bot.db import init_db
from bjj_bot.services import users as user_service


TG_ID = 4242


@pytest.fixture()
async def seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "cli.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    await init_db(engine, db_path)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await user_service.ensure_user(
            session,
            TelegramUser(id=TG_ID, is_bot=False, first_name="Tester", username="tester"),
        )
    await engine.dispose()
    return db_path


def _run(seeded_db: Path, capsys: pytest.CaptureFixture[str], *argv: str) -> dict:
    rc = cli.main(["--db", str(seeded_db), "--telegram-id", str(TG_ID), "--json", *argv])
    out = capsys.readouterr().out
    assert rc == 0, out
    return json.loads(out)


def test_status_reports_clean_state(seeded_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = _run(seeded_db, capsys, "status")
    assert payload["user"]["telegram_id"] == TG_ID
    assert payload["progress"]["belt"] == "white"
    assert payload["progress"]["total_sessions"] == 0
    assert payload["arsenal_move_count"] == 0


def test_schema_command_runs_without_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # schema doesn't require an existing DB, so a bogus path is fine.
    rc = cli.main(["--db", str(tmp_path / "missing.sqlite3"), "--json", "schema"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert "entities" in payload
    assert "white" in payload["belts"]


def test_full_workflow_log_session_and_update_status(
    seeded_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    move = _run(
        seeded_db,
        capsys,
        "move", "add",
        "--name", "Scissor Sweep",
        "--category", "guard_closed",
        "--tags", "gi,fundamental",
        "--note", "angle first",
    )
    move_id = move["id"]
    assert move["category_name"] == "Closed Guard"
    assert move["tags"] == ["fundamental", "gi"]

    # Fuzzy match on a typo'd name should resolve to the existing move.
    logged = _run(
        seeded_db,
        capsys,
        "session", "log",
        "--date", "2026-05-12",
        "--duration", "90",
        "--move-name", "scissor swep",
        "--fuzzy-names",
    )
    assert logged["session"]["duration_minutes"] == 90
    assert logged["session"]["move_ids"] == [move_id]
    assert logged["resolved_moves"][0]["matched_id"] == move_id

    listing = _run(seeded_db, capsys, "session", "list", "--limit", "5")
    assert len(listing) == 1
    assert "Scissor Sweep" in listing[0]["summary"]

    status = _run(seeded_db, capsys, "status")
    assert status["progress"]["total_sessions"] == 1
    assert status["total_duration_minutes"] == 90


def test_session_log_rejects_unknown_name_without_fuzzy(
    seeded_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(
        seeded_db, capsys,
        "move", "add", "--name", "Knee Cut", "--category", "passing",
    )
    rc = cli.main(
        [
            "--db", str(seeded_db),
            "--telegram-id", str(TG_ID),
            "--json",
            "session", "log",
            "--move-name", "kne cu",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 2
    payload = json.loads(out)
    assert "No exact-name match" in payload["error"]


def test_promotion_flow_updates_progress(
    seeded_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(seeded_db, capsys, "session", "log", "--date", "2026-05-10")
    promo = _run(
        seeded_db, capsys, "promotion", "apply", "--kind", "stripe", "--date", "2026-05-11"
    )
    assert promo["belt"] == "white"
    assert promo["stripes"] == 1
    assert promo["session_number"] == 1

    status = _run(seeded_db, capsys, "status")
    assert status["progress"]["stripes"] == 1


def test_promotion_update_edits_date_and_rank(
    seeded_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    promo = _run(seeded_db, capsys, "promotion", "apply", "--belt", "blue", "--stripes", "0", "--date", "2026-05-01")
    updated = _run(
        seeded_db, capsys,
        "promotion", "update", str(promo["id"]),
        "--date", "2026-04-15",
        "--stripes", "2",
    )
    assert updated["promotion_date"] == "2026-04-15"
    assert updated["belt"] == "blue"
    assert updated["stripes"] == 2

    status = _run(seeded_db, capsys, "status")
    assert status["progress"]["belt"] == "blue"
    assert status["progress"]["stripes"] == 2


def test_category_create_rename_delete(
    seeded_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    created = _run(
        seeded_db, capsys,
        "category", "create", "--name", "Funky Guard", "--parent", "guard",
    )
    code = created["code"]
    assert created["parent_code"] == "guard"
    assert created["name"] == "Funky Guard"

    # Listing under "guard" now includes our new group.
    listing = _run(seeded_db, capsys, "category", "list", "--parent", "guard")
    names = {row["name"] for row in listing}
    assert "Funky Guard" in names

    # File a move into it so we exercise the cascade.
    move = _run(
        seeded_db, capsys,
        "move", "add", "--name", "Wave Sweep", "--category", code,
    )
    assert move["category_code"] == code

    # Refuses to delete without --confirm.
    rc = cli.main(
        [
            "--db", str(seeded_db), "--telegram-id", str(TG_ID), "--json",
            "category", "delete", code,
        ]
    )
    out = capsys.readouterr().out
    assert rc == 2
    err = json.loads(out)
    assert "--confirm" in err["error"]

    renamed = _run(seeded_db, capsys, "category", "rename", code, "--name", "Funky G")
    assert renamed["name"] == "Funky G"

    shown = _run(seeded_db, capsys, "category", "show", code)
    assert shown["name"] == "Funky G"
    assert [p["code"] for p in shown["path"]] == ["guard", code]

    deleted = _run(seeded_db, capsys, "category", "delete", code, "--confirm")
    assert deleted["ok"] is True

    # Move was cascaded away.
    rc = cli.main(
        [
            "--db", str(seeded_db), "--telegram-id", str(TG_ID), "--json",
            "move", "show", str(move["id"]),
        ]
    )
    capsys.readouterr()
    assert rc == 2


def test_user_init_creates_db_and_progress(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "fresh.sqlite3"
    rc = cli.main(
        [
            "--db", str(db_path), "--json",
            "user", "init",
            "--init-telegram-id", "9999",
            "--first-name", "Fresh",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    payload = json.loads(out)
    assert payload["created"] is True
    assert payload["telegram_id"] == 9999
    assert payload["progress"]["belt"] == "white"

    # Re-running is idempotent.
    rc = cli.main(
        [
            "--db", str(db_path), "--json",
            "user", "init",
            "--init-telegram-id", "9999",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    again = json.loads(out)
    assert again["created"] is False


def test_user_list_and_set_competitor(seeded_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    listing = _run(seeded_db, capsys, "user", "list")
    assert len(listing) == 1
    assert listing[0]["telegram_id"] == TG_ID
    assert listing[0]["progress"]["competitor"] is False

    toggled = _run(seeded_db, capsys, "user", "set-competitor", "--on")
    assert toggled["competitor"] is True

    cleared = _run(seeded_db, capsys, "user", "set-competitor", "--off")
    assert cleared["competitor"] is False


def test_admin_stats_reports_counts(seeded_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(seeded_db, capsys, "move", "add", "--name", "X-Pass", "--category", "passing")
    _run(seeded_db, capsys, "session", "log", "--date", "2026-05-12")
    stats = _run(seeded_db, capsys, "admin", "stats")
    assert stats["total_users"] == 1
    assert stats["total_sessions"] == 1
    assert stats["total_moves"] == 1
