"""
OAuth gate for the endpoints that actually do something (currently just
POST /emails/send).

Design choice: this is OFF by default. If GOOGLE_CLIENT_ID is blank in
.env, require_auth() is a no-op - so local dev and the test suite never
need a real Google credential. Set GOOGLE_CLIENT_ID once you deploy
publicly and it starts enforcing real sign-in automatically.
"""

import logging
from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import get_settings

logger = logging.getLogger("email_automation.auth")
settings = get_settings()


def require_auth(authorization: str | None = Header(default=None)) -> dict | None:
    if not settings.oauth_enabled:
        return None  # auth disabled - dev/test mode

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.google_client_id
        )
    except Exception as exc:
        # Covers a bad/expired token (ValueError) AND infrastructure issues
        # like failing to reach Google's cert endpoint (TransportError).
        # Either way, a protected endpoint fails closed - never open.
        logger.warning("Rejected request: could not verify Google ID token (%s)", exc)
        raise HTTPException(status_code=401, detail="Invalid or unverifiable token.") from exc

    return claims
