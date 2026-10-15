"""
Tests mock claude_service so they run without a real API key or network
access. A temporary SQLite DB is used for the audit log so tests never
touch app/data/emails.db. OAuth is disabled by default (no GOOGLE_CLIENT_ID
in test env), so /emails/send is reachable without a token here.
"""

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _use_temp_db():
    """Point DATABASE_URL at a throwaway file before the app is imported."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    os.environ["GOOGLE_CLIENT_ID"] = ""  # ensure OAuth is off for tests
    os.environ["DRY_RUN"] = "true"  # a dev's .env must never make tests send real mail
    os.environ["VECTOR_DB_PATH"] = tempfile.mkdtemp(prefix="chroma_test_")
    os.environ["RATE_LIMIT_AI"] = "1000/minute"
    os.environ["RATE_LIMIT_SEND"] = "1000/minute"
    yield

    try:
        from app.db import engine
        engine.dispose()
    except Exception:
        pass

    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def client(_use_temp_db):
    # Skip the embedding-model download during tests.
    with patch("app.services.rag_service.seed_default_templates"):
        from app.main import app

        with TestClient(app) as c:
            yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "dry_run" in body
    assert body["oauth_enabled"] is False


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200


@patch("app.routers.emails.claude_service.classify_email")
def test_classify(mock_classify, client):
    mock_classify.return_value = {
        "category": "support",
        "priority": "high",
        "sentiment": "negative",
        "reasoning": "Customer reports a broken feature.",
    }
    resp = client.post(
        "/emails/classify",
        json={"subject": "App is broken", "body": "Nothing loads, please help."},
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "support"


@patch("app.routers.compose.claude_service.draft_email")
@patch("app.routers.compose.rag_service.retrieve_similar")
def test_compose(mock_retrieve, mock_draft, client):
    mock_retrieve.return_value = ["Hi {name}, following up..."]
    mock_draft.return_value = {
        "subject": "Following up on our proposal",
        "body": "Hi John, just checking in on the proposal I sent last week.",
    }
    resp = client.post(
        "/compose",
        json={
            "goal": "Follow up on a proposal sent last week",
            "recipient_name": "John",
            "tone": "friendly",
            "key_points": ["mention the deadline"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Following up" in body["subject"]
    assert body["context_used"] == ["Hi {name}, following up..."]


def test_send_dry_run_no_oauth(client):
    """OAuth is disabled in test env, so this should succeed without a token."""
    resp = client.post(
        "/emails/send",
        json={"to": "test@example.com", "subject": "Hello", "body": "Test body"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "dry_run"


@patch("app.routers.emails.claude_service.classify_email")
def test_logs_endpoint_records_activity(mock_classify, client):
    mock_classify.return_value = {
        "category": "personal",
        "priority": "low",
        "sentiment": "neutral",
        "reasoning": "Routine message.",
    }
    client.post("/emails/classify", json={"subject": "Hi", "body": "Just saying hello."})
    resp = client.get("/logs?limit=5")
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "classify"


# ---------- JSON parsing / normalisation (the usual cause of 502s) ----------

def test_extract_json_handles_preamble_and_fences():
    from app.services.claude_service import _extract_json

    assert _extract_json('Sure! Here it is:\n{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_classification_is_normalised():
    from app.services.claude_service import _normalise_classification

    out = _normalise_classification({"category": "Support", "priority": "HIGH", "sentiment": "weird"})
    assert out == {"category": "support", "priority": "high", "sentiment": "neutral", "reasoning": ""}


@patch("app.services.claude_service._call_claude")
def test_classify_survives_messy_model_output(mock_call, client):
    mock_call.return_value = 'Here you go:\n{"category": "Sales", "priority": "Low", "sentiment": "Positive", "reasoning": "Pitch."}'
    resp = client.post("/emails/classify", json={"subject": "Offer", "body": "Buy now"})
    assert resp.status_code == 200
    assert resp.json()["category"] == "sales"


@patch("app.routers.emails.claude_service.classify_email", side_effect=RuntimeError("boom"))
def test_classify_upstream_failure_is_502(_mock, client):
    resp = client.post("/emails/classify", json={"subject": "x", "body": "y"})
    assert resp.status_code == 502


@patch("app.routers.emails.claude_service.draft_reply")
@patch("app.routers.emails.claude_service.classify_email")
def test_reply(mock_classify, mock_draft, client):
    mock_classify.return_value = {"category": "support", "priority": "high", "sentiment": "negative", "reasoning": "r"}
    mock_draft.return_value = {"subject": "Re: Help", "body": "We are on it."}
    resp = client.post("/emails/reply", json={"incoming_subject": "Help", "incoming_body": "Broken"})
    assert resp.status_code == 200
    assert resp.json()["classification"]["category"] == "support"


# ---------- input validation ----------

def test_send_rejects_newline_in_subject(client):
    resp = client.post("/emails/send", json={"to": "a@b.com", "subject": "hi\nBcc: x@y.com", "body": "b"})
    assert resp.status_code == 422


def test_classify_rejects_huge_body(client):
    resp = client.post("/emails/classify", json={"subject": "x", "body": "a" * 20001})
    assert resp.status_code == 422


# ---------- auth ----------

def test_auth_allowlist(monkeypatch):
    from fastapi import HTTPException

    from app import auth

    monkeypatch.setattr(auth.settings, "google_client_id", "client-id")
    monkeypatch.setattr(auth.settings, "allowed_emails", "me@example.com")

    def fake_verify(token, req, cid):
        return {"email": "other@example.com" if token == "bad" else "me@example.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", fake_verify)

    assert auth.require_auth("Bearer good")["email"] == "me@example.com"
    with pytest.raises(HTTPException) as e:
        auth.require_auth("Bearer bad")
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        auth.require_auth(None)
    assert e.value.status_code == 401


def test_auth_fails_closed_without_allowlist(monkeypatch):
    from fastapi import HTTPException

    from app import auth

    monkeypatch.setattr(auth.settings, "google_client_id", "client-id")
    monkeypatch.setattr(auth.settings, "allowed_emails", "")
    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", lambda *a: {"email": "x@y.com", "email_verified": True})
    with pytest.raises(HTTPException) as e:
        auth.require_auth("Bearer t")
    assert e.value.status_code == 403


def test_rag_disabled_returns_no_context(monkeypatch):
    from app.services import rag_service

    monkeypatch.setattr(rag_service.settings, "rag_enabled", False)
    assert rag_service.retrieve_similar("anything") == []
    rag_service.seed_default_templates()  # must not touch Chroma
    with pytest.raises(RuntimeError):
        rag_service.add_template("t", "b", [])
