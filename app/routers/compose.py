import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.models import ComposeRequest, ComposeResponse, TemplateIn
from app.services import claude_service, rag_service, log_service
from app.db import get_db
from app.config import get_settings
from app.rate_limit import limiter

logger = logging.getLogger("email_automation.router.compose")
settings = get_settings()
router = APIRouter(prefix="/compose", tags=["compose"])


@router.post("", response_model=ComposeResponse)
@limiter.limit(settings.rate_limit_compose)
def compose(request: Request, payload: ComposeRequest, db: Session = Depends(get_db)):
    try:
        context_snippets: list[str] = []
        if payload.use_rag_context:
            context_snippets = rag_service.retrieve_similar(payload.goal, top_k=2)

        draft = claude_service.draft_email(
            goal=payload.goal,
            tone=payload.tone,
            recipient_name=payload.recipient_name,
            key_points=payload.key_points,
            context_snippets=context_snippets,
        )
        log_service.record(
            db,
            direction="outgoing",
            action="compose",
            subject=draft["subject"],
            body=draft["body"],
            status="drafted",
        )
        return ComposeResponse(
            subject=draft["subject"],
            body=draft["body"],
            context_used=context_snippets,
        )
    except Exception as exc:
        logger.exception("Compose failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/templates", status_code=201)
def add_template(payload: TemplateIn):
    doc_id = rag_service.add_template(payload.title, payload.body, payload.tags)
    return {"id": doc_id, "status": "stored"}
