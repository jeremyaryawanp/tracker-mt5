# Setup Guide

## Local (SQLite)

```bash
uv sync                      # Python 3.12 + dependencies
cp .env.example .env         # adjust values; never commit .env
uv run uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000. API docs: http://127.0.0.1:8000/api/docs.
Migrations run automatically on startup (`AUTO_MIGRATE=true`). To run them manually:

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"   # after model changes
```

## Docker Compose (PostgreSQL)

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/api/v1/health
```

The app is published on `127.0.0.1:8000` only. If Docker Hub rate-limits pulls, use a mirror:

```bash
POSTGRES_IMAGE=mirror.gcr.io/library/postgres:16-alpine \
PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim docker compose up --build -d
```

## Authentication

When `APP_HOST` is not a loopback address the app refuses to start without `ADMIN_PASSWORD_HASH`:

```bash
uv run python scripts/hash_password.py   # paste output into ADMIN_PASSWORD_HASH
```

## Checks

```bash
uv run ruff check .
uv run pytest
```
