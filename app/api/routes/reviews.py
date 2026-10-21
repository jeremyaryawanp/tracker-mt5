from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.services.accounts import get_account
from app.services.reporting import llm
from app.services.reporting.review import REFLECTION_FIELDS, build_review, get_review, save_review

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReflectionIn(BaseModel):
    performance_summary: str | None = Field(None, max_length=20000)
    strengths: str | None = Field(None, max_length=20000)
    mistakes: str | None = Field(None, max_length=20000)
    repeated_mistakes: str | None = Field(None, max_length=20000)
    lessons_learned: str | None = Field(None, max_length=20000)
    improvement_plan: str | None = Field(None, max_length=20000)
    stop_doing: str | None = Field(None, max_length=20000)
    continue_doing: str | None = Field(None, max_length=20000)
    next_week_goals: str | None = Field(None, max_length=20000)


def _check_account(db, user, account_id):
    if account_id is not None and get_account(db, user, account_id) is None:
        raise HTTPException(404, "Account not found")


def _payload(db, user, week, account_id):
    data = build_review(db, user, week, [account_id] if account_id else None)
    r = get_review(db, user, data["week_start"], account_id)
    data["reflection"] = ({f: getattr(r, f) for f in REFLECTION_FIELDS} if r else None)
    data["llm_summary"] = r.llm_summary if r else None
    return data


@router.get("/weekly")
def weekly(week: date, account_id: int | None = Query(None),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_account(db, user, account_id)
    return jsonable_encoder(_payload(db, user, week, account_id))


@router.put("/weekly")
def save(week: date, body: ReflectionIn, account_id: int | None = Query(None),
         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_account(db, user, account_id)
    data = build_review(db, user, week, [account_id] if account_id else None)
    save_review(db, user, data, body.model_dump(exclude_unset=True), account_id)
    db.commit()
    return jsonable_encoder(_payload(db, user, week, account_id))


@router.post("/weekly/llm-summary")
def llm_summary(week: date, request: Request, account_id: int | None = Query(None),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_account(db, user, account_id)
    data = build_review(db, user, week, [account_id] if account_id else None)
    try:
        text = llm.generate_summary(request.app.state.settings, data,
                                    getattr(request.app.state, "llm_transport", None))
    except llm.LlmUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    save_review(db, user, data, {"llm_summary": text}, account_id)
    db.commit()
    return {"llm_summary": text}
