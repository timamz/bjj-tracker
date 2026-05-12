# Agent Interface (`bjj-cli`)

A synchronous, JSON-friendly wrapper over the same service layer that the
Telegram bot uses. Designed so an LLM assistant can take a user message like
"log today's BJJ class, 90 min, worked guard retention" and translate it into
safe, structured commands without needing to read the bot's source.

The bot keeps working exactly as before — `bjj-cli` only adds a new entry
point that opens the same SQLite database.

## Install

The CLI is installed automatically by `uv sync` (or `pip install -e .`):

```bash
uv sync --extra dev
.venv/bin/bjj-cli --help
# or as a module:
.venv/bin/python -m bjj_bot.cli --help
```

## Selecting the database and user

`bjj-cli` resolves these in order:

| What | Source |
| --- | --- |
| Database file | `--db PATH` → `$BJJ_DB_PATH` → `$DB_PATH` → `./data/bjj_bot.sqlite3` → `/data/bjj_bot.sqlite3` |
| Telegram user | `--telegram-id N` → `$OWNER_ID` → `$BJJ_OWNER_ID` → the sole user, if exactly one exists |

The user must have `/start`ed the bot at least once so their `users` row
exists; the CLI will not create new Telegram accounts.

## Output modes

- Default: short human-readable text.
- `--json`: structured JSON to stdout. Errors become `{"error": "..."}` and the
  process exits with code `2`. **Agents should always pass `--json`.**

## Commands at a glance

```bash
bjj-cli --json schema              # data-model summary; safe even without a DB
bjj-cli --json status              # current belt, totals, last update
bjj-cli --json history --limit 10  # combined session+promotion timeline

bjj-cli --json session log --date today --duration 90 \
    --move-name "scissor sweep" --move-name "knee cut" --fuzzy-names
bjj-cli --json session list --limit 10
bjj-cli --json session show 42
bjj-cli --json session update 42 --duration 75
bjj-cli --json session delete 42

bjj-cli --json move list --category guard_closed
bjj-cli --json move list --recent --limit 8
bjj-cli --json move search "knee cut"
bjj-cli --json move show 17
bjj-cli --json move add --name "Hip Bump Sweep" --category guard_closed \
    --tags gi,fundamental --note "post the hand"
bjj-cli --json move update 17 --note "trap the wrist" --tags gi
bjj-cli --json move delete 17

bjj-cli --json category list                   # roots
bjj-cli --json category list --parent guard    # children of "guard"
bjj-cli --json category show guard_closed      # path + children
bjj-cli --json category create --name "Funky Guard" --parent guard
bjj-cli --json category rename <code> --name "Worm Guard"
bjj-cli --json category delete <code> --confirm   # cascades to sub-groups + moves

bjj-cli --json promotion list
bjj-cli --json promotion apply --kind stripe --date today
bjj-cli --json promotion apply --belt blue --stripes 0 --date 2026-05-12
bjj-cli --json promotion update 3 --date 2026-05-12 --stripes 2
bjj-cli --json promotion delete 3

bjj-cli --json user init --init-telegram-id 12345 --first-name Tima
bjj-cli --json user list
bjj-cli --json user set-competitor --on

bjj-cli --json admin stats         # mirrors /admin owner panel
```

`session`, `move`, `category` (groups), `promotion`, and `user` subgroups expose
every CRUD operation the bot offers, so direct usage via the Telegram UI and
CLI stay in sync — both write through `bjj_bot.services.*`.

## Bot ↔ CLI coverage matrix

| Bot action | CLI command |
| --- | --- |
| `/start`, first-touch user creation | `user init` (idempotent; creates DB if missing) |
| Me / Info / belt view | `status`, `history` |
| Toggle competitor flag | `user set-competitor --on/--off` |
| Upgrade (stripe / belt) | `promotion apply --kind stripe|belt` |
| Pick explicit rank from picker | `promotion apply --belt X --stripes N` |
| Edit promotion date | `promotion update <id> --date` |
| Edit promotion rank | `promotion update <id> --belt --stripes` |
| Delete promotion | `promotion delete <id>` |
| Promotion history | `promotion list`, `history` |
| Log session (date picker → moves → duration) | `session log` |
| View / list session history | `session list`, `session show`, `history` |
| Edit session date / duration / moves | `session update` |
| Delete session | `session delete` |
| Library: browse categories | `category list [--parent CODE]`, `category show CODE` |
| Library: add group (sub-category) | `category create --name --parent` |
| Library: rename group | `category rename CODE --name` |
| Library: delete group (cascades) | `category delete CODE --confirm` |
| Add move | `move add` |
| Edit move name / group / note / tags | `move update` |
| Delete move | `move delete` |
| Search moves | `move search QUERY` |
| Recent moves | `move list --recent` |
| Owner `/admin` stats | `admin stats` |
| Rank emoji capture (`/rankemojiids`) | *not exposed* — owner-only emoji wiring, edits `.env` outside the DB |

## Mapping natural language to commands

The CLI does *not* parse natural language; the calling agent does. A useful
loop:

1. `bjj-cli --json schema` — read the data model.
2. `bjj-cli --json category list` (and `--parent` to drill in) — learn the
   taxonomy you can file new moves under.
3. `bjj-cli --json move list` — see the user's existing arsenal so you can
   match references in their message to known moves.
4. `bjj-cli --json session log ...` — record the class.

### Worked example

User says: *"log today's BJJ class, 90 min, sparring, felt tired, worked guard retention"*

Reasonable agent translation:

```bash
# Try to match "guard retention" to an existing move.
bjj-cli --json move search "guard retention"
```

If a match returns:

```bash
bjj-cli --json session log --date today --duration 90 \
    --move-id <matched id>
```

If no match returns, either create the move first:

```bash
bjj-cli --json move add --name "Guard Retention" --category guard_open \
    --note "felt tired today"
bjj-cli --json session log --date today --duration 90 \
    --move-name "Guard Retention"
```

…or log the session with just a duration and no moves:

```bash
bjj-cli --json session log --date today --duration 90
```

> **Limitation:** `training_sessions` has no free-text column. Encode "felt
> tired" / "sparring intensity" remarks either on a move's `note` field or
> outside the tracker. Listed in `schema` output.

### Worked example: *"show last 10 sessions"*

```bash
bjj-cli --json session list --limit 10
```

## Error contract

- Exit code `0`: success. Stdout is valid JSON (or human text without
  `--json`).
- Exit code `2`: a `CliError` — bad input, missing row, schema violation.
  With `--json` the body is `{"error": "<message>"}`.
- Any other exit code: unexpected exception; surface to the user.

The CLI never modifies users it doesn't recognise and never invents
categories — agents can call it without fear of corrupting the DB shape.

## Testing the wrapper

```bash
.venv/bin/python -m pytest tests/test_cli.py -v
```

Covers: `status`, `schema`, end-to-end log + status, fuzzy-name rejection,
promotion flow, `promotion update`, category CUD with cascade, `user init` on a
fresh DB, `user list`, `user set-competitor`, `admin stats`.

## Limitations

- `training_sessions` has no free-text notes column. Encode "felt tired" remarks
  on a practiced move's `note` or outside the tracker.
- Categories are seeded from `taxonomy.CATEGORY_SEEDS`, but users (and the CLI)
  may also create, rename, and delete their own groups under any parent.
  Deleting a group cascades to all descendant groups and the moves filed under
  them — `category delete` requires `--confirm` to acknowledge this.
- The CLI mirrors `update_promotion`/`apply_promotion` validation, so it
  refuses invalid stripe counts or unknown belts via a `CliError`.
- `/rankemojiids` (owner-only emoji capture) is not exposed — it edits
  configuration, not DB rows.
