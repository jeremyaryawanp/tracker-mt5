from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.api.dependencies import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001
        db_status = "unavailable"
        response.status_code = 503
    return {"status": "ok" if db_status == "ok" else "degraded", "database": db_status,
            "version": __version__}
