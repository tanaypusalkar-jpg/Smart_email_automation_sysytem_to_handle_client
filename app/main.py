import logging
from contextlib import asynccontextmanager
from typing import cast, Callable

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import get_settings
from app.models import HealthResponse, LogEntryOut
from app.routers import emails, compose
from app.services import rag_service
from app.rate_limit import limiter
from app.db import init_db, get_db
from app.models_db import EmailLog

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("email_automation")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()

    try:
        rag_service.seed_default_templates()
    except Exception:
        # Chroma's default embedder downloads a model file on first use.
        # On a locked-down network that download can fail. RAG context is
        # a nice-to-have for /compose, not something that should take the
        # whole API down.
        logger.exception(
            "Could not seed the vector store (RAG context will be unavailable). "
            "The rest of the API still works."
        )

    logger.info(
        "Email Automation System started. dry_run=%s oauth_enabled=%s",
        settings.dry_run,
        settings.oauth_enabled,
    )
    yield


app = FastAPI(
    title="Email Automation System",
    description="Classifies, drafts, and sends email replies using the Claude API, "
    "with a RAG layer, a persistent audit log, rate limiting, and an OAuth gate on send.",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded, 
    cast(Callable, _rate_limit_exceeded_handler)
)
app.add_middleware(SlowAPIMiddleware)

# Wide-open CORS for local dev so the showcase website can call the API
# directly from a different port. Lock this to your real deployed domain
# once you have one - see README's security checklist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(emails.router)
app.include_router(compose.router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        claude_configured=bool(settings.anthropic_api_key),
        smtp_configured=bool(settings.smtp_username and settings.smtp_password),
        oauth_enabled=settings.oauth_enabled,
        dry_run=settings.dry_run,
    )


@app.get("/logs", response_model=list[LogEntryOut])
def get_logs(limit: int = 20, db: Session = Depends(get_db)) -> list[LogEntryOut]:
    """Recent audit log entries - what got classified/drafted/sent, most recent first."""
    rows = db.execute(
        select(EmailLog).order_by(EmailLog.created_at.desc()).limit(min(limit, 200))
    ).scalars().all()
    return [
        LogEntryOut(
            id=r.id,
            direction=r.direction,
            action=r.action,
            subject=r.subject,
            category=r.category,
            priority=r.priority,
            status=r.status,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@app.get("/")
def root() -> dict:
    return {
        "message": "Email Automation System API is running.",
        "docs": "/docs",
        "health": "/health",
    }