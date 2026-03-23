# BJJ Bot

## Deployment

Deployments target the devbox at `89.125.54.222` (user: `root`). Use Docker context:

```bash
# Deploy
DOCKER_CONTEXT=devbox docker compose up --build -d
```

Data on the devbox is stored at `/home/timamz/dev/bjj-tracker/data` (bound via named volume `bjj_data`).

## Proxy

The bot supports an optional `PROXY_URL` env var (e.g. `socks5://user:pass@host:port`) for routing all Telegram API traffic through a proxy. Set it in `.env`.
