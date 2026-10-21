from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_database


def get_db() -> Iterator[Session]:
    with get_database().session() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
