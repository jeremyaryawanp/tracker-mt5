from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.mock.adapter import MockAdapter
from app.models import TradingAccount, User
from app.models.enums import Platform
from app.services.accounts import create_account
from app.services.synchronization.ingest import ingest_batch


def load_demo_account(session: Session, user: User, *, seed: int = 42,
                      adapter: MockAdapter | None = None) -> TradingAccount:
    """Create (or refresh) a SIMULATED account populated by the mock adapter."""
    adapter = adapter or MockAdapter(seed=seed)
    batch = adapter.fetch_batch()
    account = session.scalar(select(TradingAccount).where(
        TradingAccount.user_id == user.id, TradingAccount.platform == Platform.MOCK,
        TradingAccount.login_hash == batch.account.login_hash))
    if account is None:
        account, _ = create_account(
            session, user, account_name=f"Demo account (simulated, seed {seed})",
            platform=Platform.MOCK, account_currency="USD", is_simulated=True,
            login_hash=batch.account.login_hash)
        account.initial_balance = Decimal(adapter.initial_balance)
    ingest_batch(session, account, batch)
    _apply_demo_annotations(session, account, adapter.annotations)
    session.commit()
    return account


def _apply_demo_annotations(session: Session, account: TradingAccount, data: dict) -> None:
    try:
        from app.services.journal import apply_simulated_annotations
    except ImportError:  # journal service lands in TASK-008
        return
    apply_simulated_annotations(session, account, data)
