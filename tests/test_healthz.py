"""Endpoint contract tests for the FastAPI server.

Covers:
- /api/healthz happy path (主办方 SSH probe; Spec C §2.1)
- 4xx negative paths for the cheapest validation guards (no LLM calls):
  - /api/coach/onboard      400 on empty user_message
  - /api/profile/parse      400 on text < 50 chars
  - /api/interviewer/next   400 on empty answer
  - /api/coach/review       404 on unknown session_id
  - /                       200 (root serves index.html or JSON fallback)

These short-circuit BEFORE any DeepSeek call, so they cost zero tokens
and run in <1s. They guard against the most likely refactor regression
(losing a manual validator that lives in raw Python rather than Pydantic).
"""
from fastapi.testclient import TestClient

from server.main import app


# ---------- /api/healthz ----------

def test_healthz_returns_ok():
    with TestClient(app) as client:
        resp = client.get("/api/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["provider"] == "deepseek"
        assert body["version"] == "v2-mvp"
        assert "commit_hash" in body
        assert "deploy_time" in body


def test_healthz_commit_hash_nonempty():
    """commit_hash should be either a short SHA or 'unknown' (never empty)."""
    with TestClient(app) as client:
        body = client.get("/api/healthz").json()
        assert isinstance(body["commit_hash"], str)
        assert len(body["commit_hash"]) > 0


# ---------- root ----------

def test_root_returns_200():
    """/ serves index.html (FileResponse) when web/ exists, else JSON fallback."""
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200


# ---------- negative paths (no LLM cost) ----------

def test_coach_onboard_empty_message_400():
    """/api/coach/onboard short-circuits before LLM when user_message is blank."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/coach/onboard",
            json={"user_message": "   ", "history": []},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()


def test_profile_parse_too_short_400():
    """/api/profile/parse rejects text < 50 chars without hitting DeepSeek."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/profile/parse",
            json={"raw_project_text": "短文本"},
        )
        assert resp.status_code == 400
        assert "too short" in resp.json()["detail"].lower()


def test_interviewer_next_empty_answer_400():
    """/api/interviewer/next rejects empty answers before touching the store."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/interviewer/next",
            json={"session_id": "irrelevant", "answer": ""},
        )
        assert resp.status_code == 400


def test_coach_review_unknown_session_404():
    """/api/coach/review returns 404 (not 500) for nonexistent session_id."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/coach/review",
            json={"session_id": "definitely-not-a-real-session"},
        )
        assert resp.status_code == 404


def test_interviewer_next_unknown_session_404_with_structured_detail():
    """Spec C §2.6: 404 must have detail = {error, message}, not a flat string.

    The frontend renders this as the chat error and depends on the shape.
    """
    with TestClient(app) as client:
        resp = client.post(
            "/api/interviewer/next",
            json={"session_id": "no-such-session", "answer": "anything"},
        )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert isinstance(detail, dict), \
            f"Spec C §2.6 requires dict-shaped detail, got {type(detail)}"
        assert detail.get("error") == "session_expired"
        assert "message" in detail
