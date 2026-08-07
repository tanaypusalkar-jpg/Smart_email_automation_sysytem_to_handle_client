import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.models import (
    ClassifyRequest,
    ClassifyResponse,
    SendRequest,
    SendResponse,
    ReplyRequest,
    ReplyResponse,
)
from app.services import claude_service, email_service, log_service
from app.db import get_db
from app.auth import require_auth
from app.config import get_settings
from app.rate_limit import limiter

logger = logging.getLogger("email_automation.router.emails")
settings = get_settings()
router = APIRouter(prefix="/emails", tags=["emails"])


@router.post("/classify", response_model=ClassifyResponse)
def classify(payload: ClassifyRequest, db: Session = Depends(get_db)):
    try:
        result = claude_service.classify_email(payload.subject, payload.body)
        log_service.record(
            db,
            direction="incoming",
            action="classify",
            subject=payload.subject,
            body=payload.body,
            status="drafted",
            category=result.get("category"),
            priority=result.get("priority"),
        )
        return ClassifyResponse(**result)
    except Exception as exc:
        logger.exception("Classification failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/reply", response_model=ReplyResponse)
def reply(payload: ReplyRequest, db: Session = Depends(get_db)):
    try:
        classification = claude_service.classify_email(
            payload.incoming_subject, payload.incoming_body
        )
        draft = claude_service.draft_reply(
            incoming_subject=payload.incoming_subject,
            incoming_body=payload.incoming_body,
            sender_name=payload.sender_name,
            tone=payload.tone,
            instructions=payload.instructions,
        )
        log_service.record(
            db,
            direction="outgoing",
            action="reply",
            subject=draft["subject"],
            body=draft["body"],
            status="drafted",
            category=classification.get("category"),
            priority=classification.get("priority"),
        )
        return ReplyResponse(
            subject=draft["subject"],
            body=draft["body"],
            classification=ClassifyResponse(**classification),
        )
    except Exception as exc:
        logger.exception("Reply drafting failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/send", response_model=SendResponse)
@limiter.limit(settings.rate_limit_send)
async def send(
    request: Request,
    payload: SendRequest,
    db: Session = Depends(get_db),
    _claims: dict | None = Depends(require_auth),
):
    try:
        status, detail = await email_service.send_email(payload.to, payload.subject, payload.body)
        log_service.record(
            db,
            direction="outgoing",
            action="send",
            subject=payload.subject,
            body=payload.body,
            status=status,
        )
        return SendResponse(status=status, detail=detail)
    except RuntimeError as exc:
        log_service.record(
            db,
            direction="outgoing",
            action="send",
            subject=payload.subject,
            body=payload.body,
            status="error",
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
