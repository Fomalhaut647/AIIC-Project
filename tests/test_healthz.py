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


# ---------- /api/interviewer/start?demo=1 (Spec C §8.2) ----------

# Minimal valid payload for /interviewer/start. All fields below are
# Pydantic-required by InterviewPacket / UserModel; values are arbitrary
# since demo=1 mode bypasses the LLM that would normally consume them.
_DEMO_START_BODY = {
    "interview_packet": {
        "target": "求职",
        "interviewer_style": "直接",
        "intensity": "中",
        "project_summary": "AI 财会助理 LedgerCraft (demo fixture)",
        "focus_slots": ["S3", "S4"],
    },
    "user_model": {
        "id": "test-user",
        "goal": "求职 AI 算法实习",
        "target": "求职",
    },
}


def test_interviewer_start_demo_mode_returns_hardcoded_question():
    """Spec C §8.2: ?demo=1 returns a hardcoded S1 question without LLM call.

    This makes the demo video's first 30s deterministic. Verifies (a) endpoint
    accepts the query param, (b) returns S1_motivation state, (c) hardcoded
    question contains the expected motif (痛点 / 真实), (d) interviewer_os
    is fully populated, (e) focus_slots is the demo-specific override.
    """
    with TestClient(app) as client:
        resp = client.post(
            "/api/interviewer/start?demo=1",
            json=_DEMO_START_BODY,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "S1_motivation"
        assert "痛点" in body["question"] and "真实" in body["question"]
        assert body["session_id"]  # non-empty session created
        assert body["focus_slots"] == ["pain_real", "target_user"]
        os_ = body["interviewer_os"]
        for field in ("hidden_concern", "why_this_question",
                      "missing_slots", "what_i_want_to_hear", "risk_level"):
            assert field in os_, f"interviewer_os missing {field}"


def test_interviewer_start_demo_mode_creates_session_for_followup():
    """The demo session_id must be usable in subsequent /interviewer/next
    calls (i.e. the hardcoded turn was actually persisted to the store)."""
    with TestClient(app) as client:
        sid = client.post(
            "/api/interviewer/start?demo=1",
            json=_DEMO_START_BODY,
        ).json()["session_id"]
        # session is real → /coach/review on a 1-turn session must hit the
        # spec C §2.7 gate (state != DONE AND turns < 6 → 400), NOT 404.
        # If session weren't persisted, we'd get 404 instead.
        review_resp = client.post(
            "/api/coach/review", json={"session_id": sid},
        )
        assert review_resp.status_code == 400, \
            f"expected 400 (gate), got {review_resp.status_code}: {review_resp.text}"


# ---------- /api/coach/review tightened gate (Spec C §2.7) ----------

def test_coach_review_partial_session_400_state_and_turns_in_detail():
    """Spec C §2.7 gate: when state != DONE AND turns < 6, 400 with detail
    that helps the frontend render a useful Chinese message (Issue 3 fix).
    """
    with TestClient(app) as client:
        # Create a session via the demo path (1 turn, state=S1_motivation)
        sid = client.post(
            "/api/interviewer/start?demo=1",
            json=_DEMO_START_BODY,
        ).json()["session_id"]
        resp = client.post("/api/coach/review", json={"session_id": sid})
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        # Must mention both state and turn count so frontend can show
        # actionable feedback rather than a generic "400 Bad Request".
        assert "state=" in detail
        assert "turns=" in detail
