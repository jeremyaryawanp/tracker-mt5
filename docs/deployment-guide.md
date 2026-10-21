# Deployment Guide

Target: a single user on a home PC, Windows VPS, or small Linux server, with the MT5 terminal +
collector on Windows and the web app next to it or on the LAN.

## 1. Configure

```bash
cp .env.example .env
uv run python scripts/hash_password.py          # paste output into ADMIN_PASSWORD_HASH
python -c "import secrets; print(secrets.token_urlsafe(48))"   # APP_SECRET_KEY
```

Required for anything other than `127.0.0.1`: `ADMIN_PASSWORD_HASH` (the app refuses to start on a
non-loopback host without it) and, with `APP_ENV=production`, a non-default `APP_SECRET_KEY`.
Set `POSTGRES_PASSWORD` for Compose.

## 2. Run with Docker Compose (PostgreSQL)

```bash
docker compose up -d --build
curl http://127.0.0.1:8000/api/v1/health      # {"status":"ok","database":"ok",...}
```

If Docker Hub rate-limits pulls, use mirrors:
`PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim POSTGRES_IMAGE=mirror.gcr.io/library/postgres:16-alpine docker compose up -d --build`.

Compose publishes on `127.0.0.1:8000` only. To reach it from the LAN or internet, put a TLS
reverse proxy (Caddy / nginx) in front, set `APP_ENV=production` (secure cookies + HSTS), and keep
the port bound to localhost. Migrations run automatically at startup (`AUTO_MIGRATE=true`).

## 3. Connect MetaTrader

1. Accounts & Sync → Add account → copy the collector token (shown once).
2. MT5: on the Windows terminal machine `pip install MetaTrader5 httpx pydantic`, then
   `python -m collector.mt5_collector --url http://<app>:8000 --token <token> --days 365` for a
   backfill and add `--loop 300` for periodic sync. See `docs/metatrader-integration.md`.
3. MT4: attach `collector/mt4/TradeJournalExporter.mq4`, add the app URL to
   *Tools → Options → Expert Advisors → Allow WebRequest*, set the token input.
4. Or upload a CSV statement on Accounts & Sync.

## Security notes

- Read-only: no code path sends trading requests; a test statically scans the collector.
- Broker passwords are never stored or transmitted; logins are stored only as SHA-256 hashes.
- Collector tokens are stored hashed, rotatable, scoped to one account, rate limited.
- Session cookie is signed, `SameSite=Lax`, `Secure` in production. State-changing requests from
  other origins are rejected (Origin / `Sec-Fetch-Site` checks); CSP, `X-Frame-Options: DENY`,
  `nosniff` headers are set. Login attempts are rate limited per IP.
- Optional LLM summaries are off by default and only receive aggregated metrics.
- Rate limiters are in-process: run a single app process (default).

## Backups

`docker compose exec db pg_dump -U tradejournal tradejournal > backup.sql`. Raw deals are the
source of truth; positions can be rebuilt (`POST /api/v1/accounts/{id}/rebuild`), annotations and
reviews live in their own tables and must be backed up.
