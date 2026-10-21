import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestToken, TradingAccount, User
from app.models.enums import Platform, ServerOffsetMode
from app.security import hash_token, new_token


def create_account(
    session: Session,
    user: User,
    *,
    account_name: str,
    platform: Platform,
    account_currency: str = "USD",
    server_utc_offset_mode: ServerOffsetMode = ServerOffsetMode.AUTO,
    server_utc_offset_minutes: int | None = None,
    is_simulated: bool = False,
    login_hash: str | None = None,
) -> tuple[TradingAccount, str]:
    """Create an account plus its first ingest token. The plaintext token is returned once."""
    account = TradingAccount(
        user_id=user.id,
        account_name=account_name,
        platform=platform,
        login_hash=login_hash or f"pending:{secrets.token_hex(8)}",
        account_currency=account_currency.upper(),
        server_utc_offset_mode=server_utc_offset_mode,
        server_utc_offset_minutes=server_utc_offset_minutes,
        is_simulated=is_simulated,
    )
    session.add(account)
    session.flush()
    token = issue_token(session, account)
    return account, token


def issue_token(session: Session, account: TradingAccount, label: str = "collector") -> str:
    """Revoke active tokens for the account and issue a new one."""
    now = datetime.now(UTC)
    for existing in account.tokens:
        if existing.revoked_at is None:
            existing.revoked_at = now
    token = new_token()
    session.add(IngestToken(account_id=account.id, token_hash=hash_token(token), label=label))
    session.flush()
    return token


def resolve_token(session: Session, token: str) -> TradingAccount | None:
    row = session.scalar(
        select(IngestToken).where(
            IngestToken.token_hash == hash_token(token), IngestToken.revoked_at.is_(None)
        )
    )
    if row is None:
        return None
    row.last_used_at = datetime.now(UTC)
    return row.account


def list_accounts(session: Session, user: User) -> list[TradingAccount]:
    return list(
        session.scalars(
            select(TradingAccount)
            .where(TradingAccount.user_id == user.id)
            .order_by(TradingAccount.id)
        )
    )


def get_account(session: Session, user: User, account_id: int) -> TradingAccount | None:
    return session.scalar(
        select(TradingAccount).where(
            TradingAccount.id == account_id, TradingAccount.user_id == user.id
        )
    )
