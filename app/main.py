from fastapi import FastAPI

from app import __version__
from app.api.routes import health
from app.config import Settings, get_settings
from app.db import init_database, run_migrations
from app.frontend.app import create_frontend
from app.logging_config import configure_logging
from app.services.users import ensure_default_user


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_runtime()
    configure_logging(settings)
    if settings.auto_migrate:
        run_migrations(settings.database_url)
    db = init_database(settings)
    with db.session() as session:
        ensure_default_user(session, settings)

    api = FastAPI(
        title="TradeJournal AI API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    api.state.settings = settings
    api.include_router(health.router, prefix="/api/v1")
    api.mount("/", create_frontend(settings))
    return api
