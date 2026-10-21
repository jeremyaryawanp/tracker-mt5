from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User


def ensure_default_user(session: Session, settings: Settings) -> User:
    user = session.scalar(select(User).where(User.username == settings.admin_username))
    if user is None:
        user = User(
            username=settings.admin_username,
            display_timezone=settings.display_timezone,
            week_start=settings.week_start,
        )
        session.add(user)
    user.password_hash = settings.admin_password_hash or None
    session.commit()
    return user
