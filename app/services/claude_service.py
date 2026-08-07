"""
Thin wrapper around the Anthropic Claude API.

Everything the app asks Claude for goes through here, so retries,
JSON parsing, and error handling live in one place instead of being
copy-pasted into every router.
"""

import json
import logging
from anthropic import Anthropic, APIError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger("email_automation.claude")

settings = get_settings()
_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file before calling the API."
            )
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _call_claude(system: str, user_message: str, max_tokens: int = 1024) -> str:
    """Single point of contact with the API. Retries on transient failures."""
    client = get_client()
    try:
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
    except APIError as exc:
        logger.error("Claude API error: %s", exc)
        raise

    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts).strip()


def _extract_json(raw: str) -> dict:
    """Claude sometimes wraps JSON in ```json fences even when told not to. Strip them."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude JSON output: %s | raw=%s", exc, raw)
        raise ValueError(f"Claude did not return valid JSON: {exc}") from exc


def classify_email(subject: str, body: str) -> dict:
    system = (
        "You classify incoming emails for a busy inbox. "
        "Respond with ONLY a JSON object, no preamble, no markdown fences, matching exactly:\n"
        '{"category": "sales|support|spam|personal|other", '
        '"priority": "low|medium|high|urgent", '
        '"sentiment": "positive|neutral|negative", '
        '"reasoning": "one short sentence"}'
    )
    user_message = f"Subject: {subject}\n\nBody:\n{body}"
    raw = _call_claude(system, user_message, max_tokens=300)
    return _extract_json(raw)


def draft_email(
    goal: str,
    tone: str,
    recipient_name: str | None,
    key_points: list[str],
    context_snippets: list[str],
) -> dict:
    context_block = (
        "\n\nReference material from past emails/templates (match style, don't copy verbatim):\n"
        + "\n---\n".join(context_snippets)
        if context_snippets
        else ""
    )
    points_block = "\n".join(f"- {p}" for p in key_points) if key_points else "(none given)"

    system = (
        "You draft professional emails. Respond with ONLY a JSON object, no markdown fences:\n"
        '{"subject": "...", "body": "..."}\n'
        "The body should be ready to send as-is: correct greeting, no placeholder brackets "
        "left unfilled unless information is genuinely missing."
    )
    user_message = (
        f"Goal: {goal}\n"
        f"Tone: {tone}\n"
        f"Recipient name: {recipient_name or 'unknown - use a generic greeting'}\n"
        f"Key points to include:\n{points_block}"
        f"{context_block}"
    )
    raw = _call_claude(system, user_message, max_tokens=700)
    return _extract_json(raw)


def draft_reply(
    incoming_subject: str,
    incoming_body: str,
    sender_name: str | None,
    tone: str,
    instructions: str | None,
) -> dict:
    system = (
        "You write replies to incoming emails. Respond with ONLY a JSON object, no markdown fences:\n"
        '{"subject": "...", "body": "..."}\n'
        "Address the sender's actual points. Keep it natural, not robotic."
    )
    user_message = (
        f"Incoming email subject: {incoming_subject}\n"
        f"Incoming email body:\n{incoming_body}\n\n"
        f"Sender name: {sender_name or 'unknown'}\n"
        f"Desired tone: {tone}\n"
        f"Extra instructions: {instructions or 'none'}"
    )
    raw = _call_claude(system, user_message, max_tokens=700)
    return _extract_json(raw)
