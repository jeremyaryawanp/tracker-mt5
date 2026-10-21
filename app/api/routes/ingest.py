"""Collector endpoints. Authenticated with a per-account bearer token, never a user session."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import enforce_body_limit, get_db, get_ingest_account
from app.integrations.mt4.normalize import Mt4Ticket, tickets_to_deals
from app.models import TradingAccount
from app.models.enums import SyncSource, SyncStatus
from app.schemas.ingest import IngestAccount, IngestBatch, IngestResult
from app.services.synchronization.ingest import ingest_batch, result_of

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(enforce_body_limit)])


class Mt4Payload(BaseModel):
    account: IngestAccount
    server_utc_offset_minutes: int | None = Field(default=None, ge=-14 * 60, le=14 * 60)
    tickets: list[Mt4Ticket] = Field(default_factory=list, max_length=200_000)


def _respond(run) -> JSONResponse:
    result = result_of(run)
    code = 200 if run.status == SyncStatus.SUCCESS else 422
    return JSONResponse(result.model_dump(mode="json"), status_code=code)


@router.post("", response_model=IngestResult, responses={422: {"model": IngestResult}})
def ingest(batch: IngestBatch, account: TradingAccount = Depends(get_ingest_account),
           db: Session = Depends(get_db)):
    return _respond(ingest_batch(db, account, batch))


@router.post("/mt4", response_model=IngestResult, responses={422: {"model": IngestResult}})
def ingest_mt4(payload: Mt4Payload, account: TradingAccount = Depends(get_ingest_account),
               db: Session = Depends(get_db)):
    batch = IngestBatch(
        source=SyncSource.MT4_EA,
        account=payload.account,
        server_utc_offset_minutes=payload.server_utc_offset_minutes,
        deals=tickets_to_deals(payload.tickets),
    )
    return _respond(ingest_batch(db, account, batch))
