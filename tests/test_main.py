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
