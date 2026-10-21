from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_database
from app.models import TradingAccount, User
from app.services.accounts import get_account, resolve_token


def get_db() -> Iterator[Session]:
    with get_database().session() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Session user when auth is enabled; the default local user on loopback-only installs."""
    settings: Settings = request.app.state.settings
    user = None
    if settings.auth_enabled:
        user_id = request.session.get("user_id") if "session" in request.scope else None
        if user_id is not None:
            user = db.get(User, user_id)
    else:
        user = db.scalar(select(User).where(User.username == settings.admin_username))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return user


def get_owned_account(
    account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TradingAccount:
    account = get_account(db, user, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


def get_ingest_account(request: Request, db: Session = Depends(get_db)) -> TradingAccount:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    account = resolve_token(db, token.strip()) if scheme.lower() == "bearer" and token else None
    if account is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or revoked ingest token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    limiter = request.app.state.ingest_limiter
    if not limiter.hit(f"account:{account.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Ingest rate limit exceeded",
                            headers={"Retry-After": "60"})
    return account


def enforce_body_limit(request: Request) -> None:
    settings: Settings = request.app.state.settings
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > settings.ingest_max_bytes:
        raise HTTPException(413, "Payload too large")
