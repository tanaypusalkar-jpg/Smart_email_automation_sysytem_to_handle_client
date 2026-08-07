"""
Request/response schemas shared across routers.
"""

from typing import Literal
from pydantic import BaseModel, EmailStr, Field


class ClassifyRequest(BaseModel):
    subject: str
    body: str


class ClassifyResponse(BaseModel):
    category: Literal["sales", "support", "spam", "personal", "other"]
    priority: Literal["low", "medium", "high", "urgent"]
    sentiment: Literal["positive", "neutral", "negative"]
    reasoning: str


class ComposeRequest(BaseModel):
    goal: str = Field(..., description="What the email needs to achieve, in plain words.")
    recipient_name: str | None = None
    tone: Literal["formal", "friendly", "concise", "persuasive"] = "friendly"
    key_points: list[str] = Field(default_factory=list)
    use_rag_context: bool = Field(
        default=True, description="Pull similar past templates as style/context reference."
    )


class ComposeResponse(BaseModel):
    subject: str
    body: str
    context_used: list[str] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    incoming_subject: str
    incoming_body: str
    sender_name: str | None = None
    tone: Literal["formal", "friendly", "concise", "persuasive"] = "friendly"
    instructions: str | None = Field(
        default=None, description="Optional extra instructions, e.g. 'decline politely'."
    )


class ReplyResponse(BaseModel):
    subject: str
    body: str
    classification: ClassifyResponse | None = None


class SendRequest(BaseModel):
    to: EmailStr
    subject: str
    body: str


class SendResponse(BaseModel):
    status: Literal["sent", "dry_run"]
    detail: str


class TemplateIn(BaseModel):
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    claude_configured: bool
    smtp_configured: bool
    oauth_enabled: bool
    dry_run: bool


class LogEntryOut(BaseModel):
    id: int
    direction: str
    action: str
    subject: str
    category: str | None
    priority: str | None
    status: str
    created_at: str
