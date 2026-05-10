# BJJ Bot

## Deployment

Source-of-truth lives on devbox at `~/dev/diplom/bjj-tracker`. SSH in and work directly:

```bash
ssh timamz@100.73.138.67
cd ~/dev/diplom/bjj-tracker
git pull
docker compose up --build -d
docker compose logs -f bjj-bot
```

Data lives at `~/dev/diplom/bjj-tracker/data/` on devbox (a plain `./data:/data` bind mount in compose). The SQLite DB is at `data/bjj_bot.sqlite3`; daily backups go to `data/backups/`.

The legacy `--context devbox` workflow (compose CLI on Mac, daemon on devbox) is retired -- bind mounts no longer resolve correctly under it.

## Proxy

The bot supports an optional `PROXY_URL` env var (e.g. `socks5://user:pass@host:port`) for routing all Telegram API traffic through a proxy. Set it in `.env`.

## Backups

`scripts/backup.sh` runs inside the container (triggered by host cron via `docker exec`). Each run takes an online `sqlite3 .backup` snapshot, gzips it, writes to `/data/backups/`, and uploads to Yandex Disk WebDAV at `/bjj-bot-backups/`. Local and remote copies older than `RETENTION_DAYS` (default 30) are pruned. Failures notify `OWNER_ID` via the bot (honors `PROXY_URL`).

Required env: `YANDEX_LOGIN`, `YANDEX_APP_PASSWORD` (Yandex app password with WebDAV/"Files" scope).

Host cron on devbox (run once after deploy):

```bash
(crontab -l 2>/dev/null; echo '0 5 * * * docker exec bjj-tracker-bjj-bot-1 /app/scripts/backup.sh >> /home/timamz/bjj-backup.log 2>&1') | crontab -
```
