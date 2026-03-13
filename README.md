# BJJ Bot

Minimal, button-first Telegram bot for tracking:

- current belt and stripes
- total training sessions
- promotion history with date and session number
- personal BJJ arsenal grouped by position and technique family
- practiced arsenal moves per session

## Features

- Multi-user by Telegram account
- Adult belt progression: white, blue, purple, brown, black
- Dated session logging
- Promotion log with session snapshot
- Seeded technique taxonomy
- Per-move notes and tags
- Docker-friendly SQLite persistence on a mounted volume

## Local Run

1. Create `.env` from `.env.example`.
2. Install dependencies:

```bash
uv pip install --system -e ".[dev]"
```

3. Start the bot:

```bash
python -m bjj_bot.main
```

## Docker

```bash
docker compose up -d --build
```

The SQLite file is stored in `./data` on the host and mounted into the container at `/data`.

## Notes

- `RANK_STICKERS` accepts JSON like `{"white:0":"<file_id>"}` for optional Telegram sticker rendering.
- If no sticker is configured for a rank, the bot falls back to an emoji belt display.

