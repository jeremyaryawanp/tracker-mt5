from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select

from app.config import Settings
from app.db import Base, get_database
from app.models import User


def test_health_reports_database_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_frontend_is_mounted_and_api_routes_take_precedence(client):
    assert client.get("/").status_code == 200
    assert "TradeJournal AI" in client.get("/").text
    assert client.get("/api/openapi.json").json()["info"]["title"] == "TradeJournal AI API"


def test_migrations_match_models(app):
    engine = get_database().engine
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_default_user_created(db_session, settings):
    user = db_session.scalar(select(User).where(User.username == settings.admin_username))
    assert user is not None
    assert user.display_timezone == "Asia/Jakarta"


def test_non_loopback_host_requires_password():
    s = Settings(_env_file=None, app_host="0.0.0.0", admin_password_hash="")
    try:
        s.validate_runtime()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")
