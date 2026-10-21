from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, get_owned_account
from app.integrations.csv.adapter import CsvImportError, csv_to_batch
from app.models import SyncRun, TradingAccount, User
from app.models.enums import Platform, ServerOffsetMode
from app.schemas.accounts import (
    AccountCreate,
    AccountCreated,
    AccountOut,
    AccountUpdate,
    SyncRunOut,
)
from app.schemas.ingest import IngestResult
from app.services import accounts as svc
from app.services.synchronization.ingest import ingest_batch, result_of
from app.services.synchronization.positions import rebuild_account
from app.services.synchronization.reconcile import RetryNotPossible, reconcile, retry_sync_run

router = APIRouter(prefix="/accounts", tags=["accounts"])
MAX_CSV_BYTES = 5_000_000


@router.get("", response_model=list[AccountOut])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.list_accounts(db, user)


@router.post("", response_model=AccountCreated, status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if body.platform == Platform.MOCK:
        raise HTTPException(422, "Use POST /accounts/demo for simulated accounts")
    account, token = svc.create_account(db, user, **body.model_dump())
    db.commit()
    return AccountCreated(account=AccountOut.model_validate(account), ingest_token=token)


@router.post("/demo", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_demo_account(
    seed: int = 42, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from app.services.demo import load_demo_account

    return load_demo_account(db, user, seed=seed)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    body: AccountUpdate,
    account: TradingAccount = Depends(get_owned_account),
    db: Session = Depends(get_db),
):
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    if (account.server_utc_offset_mode == ServerOffsetMode.FIXED
            and account.server_utc_offset_minutes is None):
        raise HTTPException(422, "server_utc_offset_minutes is required for FIXED mode")
    db.commit()
    return account


@router.post("/{account_id}/token", response_model=AccountCreated)
def rotate_token(account: TradingAccount = Depends(get_owned_account),
                 db: Session = Depends(get_db)):
    token = svc.issue_token(db, account)
    db.commit()
    return AccountCreated(account=AccountOut.model_validate(account), ingest_token=token)


@router.get("/{account_id}/sync-runs", response_model=list[SyncRunOut])
def sync_runs(account: TradingAccount = Depends(get_owned_account),
              db: Session = Depends(get_db), limit: int = 50):
    return db.scalars(select(SyncRun).where(SyncRun.account_id == account.id)
                      .order_by(SyncRun.id.desc()).limit(min(max(limit, 1), 500))).all()


@router.post("/{account_id}/import/csv", response_model=IngestResult)
async def import_csv(
    file: UploadFile = File(...),
    server_utc_offset_minutes: int | None = Form(default=None),
    account: TradingAccount = Depends(get_owned_account),
    db: Session = Depends(get_db),
):
    if account.platform not in (Platform.CSV, Platform.MT4, Platform.MT5):
        raise HTTPException(422, "CSV import is not available for simulated accounts")
    data = await file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV file too large")
    try:
        batch = csv_to_batch(
            data.decode("utf-8-sig", errors="replace"),
            login_hash=account.login_hash if not account.login_hash.startswith("pending:")
            else f"csv-{account.id:08d}",
            currency=account.account_currency,
            server_utc_offset_minutes=server_utc_offset_minutes,
        )
    except CsvImportError as exc:
        raise HTTPException(422, str(exc)) from exc
    batch.account.platform = account.platform
    return result_of(ingest_batch(db, account, batch))


@router.post("/{account_id}/sync-runs/{run_id}/retry", response_model=IngestResult)
def retry_run(run_id: int, account: TradingAccount = Depends(get_owned_account),
              db: Session = Depends(get_db)):
    try:
        run = retry_sync_run(db, account, run_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RetryNotPossible as exc:
        raise HTTPException(409, str(exc)) from exc
    return result_of(run)


@router.post("/{account_id}/rebuild")
def rebuild(account: TradingAccount = Depends(get_owned_account), db: Session = Depends(get_db)):
    count = rebuild_account(db, account)
    db.commit()
    return {"positions_rebuilt": count, "reconciliation": reconcile(db, account)}


@router.get("/{account_id}/reconciliation")
def reconciliation(account: TradingAccount = Depends(get_owned_account),
                   db: Session = Depends(get_db)):
    return reconcile(db, account)
