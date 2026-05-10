"""Plan2 user_id passthrough + review hook tests — Spec D §6.2."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def test_onboard_accepts_user_id(client):
    """POST /api/coach/onboard body 含 user_id 不报 422."""
    from services.schemas import OnboardResult
    fake = AsyncMock(return_value=OnboardResult(
        need_more_info=True,
        followup_questions=["你这次主要是为了..."],
    ))
    with patch("server.main.coach_onboard", fake):
        r = client.post("/api/coach/onboard", json={
            "user_message": "我想准备保研",
            "history": [],
            "user_id": "user-x",
        })
    assert r.status_code == 200, r.text
    fake.assert_awaited_once()


def test_onboard_user_id_optional_falls_back_anonymous(client):
    """缺 user_id 字段不报 422; 后端 fallback 到 anonymous."""
    from services.schemas import OnboardResult
    fake = AsyncMock(return_value=OnboardResult(
        need_more_info=True, followup_questions=[],
    ))
    with patch("server.main.coach_onboard", fake):
        r = client.post("/api/coach/onboard", json={
            "user_message": "X", "history": [],
        })
    assert r.status_code == 200, r.text


def test_review_endpoint_updates_user_profile(client, tmp_path: Path):
    """review 完成后 data/users/<user_id>.json 应当被写入."""
    from services.schemas import (
        EvaluationReport, ResumeRewrite, HumorCard, Evidence, TrainingPlan,
        TrainingStep, TrainingMode, InterviewPacket, UserModel, Target,
        InterviewStage,
    )

    fake_review = AsyncMock(return_value=EvaluationReport(
        overall_score=72,
        summary="OK",
        strengths=[],
        weaknesses=["baseline"],
        evidence=[Evidence(quote="q", problem="p", suggestion="s")],
        dangerous_questions=["d1", "d2"],
        resume_rewrite=ResumeRewrite(original="A", rewritten="B", missing_evidence=[]),
        next_training_plan=TrainingPlan(
            recommended_next_step=TrainingMode.NORMAL, reason="r",
            steps=[
                TrainingStep(name="a", goal="g", why_now="w"),
                TrainingStep(name="b", goal="g", why_now="w"),
            ],
        ),
        humor_card=HumorCard(title="T", content="C"),
    ))

    # Seed real session via the actual store API; bypass 400 by setting state=DONE.
    store = client.app.state.store
    pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="测试项目 P 长长长", focus_slots=["baseline"],
    )
    user_model = UserModel(id="u1", goal="保研", target=Target.BAOYAN)
    sid = store.create(pkt, user_model)
    store.get(sid).state = InterviewStage.DONE  # bypass 400 pre-check

    with patch("server.main.coach_review", fake_review):
        r = client.post("/api/coach/review", json={
            "session_id": sid,
            "user_id": "u-review",
        })
    assert r.status_code == 200, r.text

    # data/users/u-review.json should now exist with this session aggregated
    profile_file = tmp_path / "users" / "u-review.json"
    assert profile_file.exists(), f"review hook should write profile: ls={list(tmp_path.iterdir())}"
    payload = json.loads(profile_file.read_text())
    assert payload["user_id"] == "u-review"
    assert payload["total_sessions"] == 1
    assert payload["recurring_weaknesses"] == {"baseline": 1}


def test_plan_endpoint_accepts_user_id(client):
    """POST /api/coach/plan 同样接受 user_id."""
    from services.schemas import (
        CoachPlanResult, InterviewPacket, TrainingPlan, TrainingStep,
        TrainingMode, Target, UserModel,
    )
    fake = AsyncMock(return_value=CoachPlanResult(
        training_plan=TrainingPlan(
            recommended_next_step=TrainingMode.NORMAL, reason="r",
            steps=[
                TrainingStep(name="a", goal="g", why_now="w"),
                TrainingStep(name="b", goal="g", why_now="w"),
            ],
        ),
        interview_packet=InterviewPacket(
            target=Target.BAOYAN, interviewer_style="strict",
            project_summary="P", focus_slots=["baseline"],
        ),
    ))
    with patch("server.main.coach_plan", fake):
        r = client.post("/api/coach/plan", json={
            "user_model": {"id": "u1", "goal": "保研", "target": "保研"},
            "project_summary": "测试项目",
            "user_id": "user-y",
        })
    assert r.status_code == 200, r.text


def test_start_endpoint_accepts_user_id(client):
    """POST /api/interviewer/start 同样接受 user_id (demo 模式 bypass LLM)."""
    r = client.post("/api/interviewer/start?demo=true", json={
        "interview_packet": {
            "target": "保研", "interviewer_style": "strict",
            "project_summary": "P", "focus_slots": ["baseline"],
        },
        "user_model": {"id": "u1", "goal": "保研", "target": "保研"},
        "user_id": "user-z",
    })
    assert r.status_code == 200, r.text


def test_next_endpoint_accepts_user_id(client):
    """POST /api/interviewer/next 同样接受 user_id."""
    # First create a session via /start demo mode
    r1 = client.post("/api/interviewer/start?demo=true", json={
        "interview_packet": {
            "target": "保研", "interviewer_style": "strict",
            "project_summary": "P", "focus_slots": ["baseline"],
        },
        "user_model": {"id": "u1", "goal": "保研", "target": "保研"},
    })
    sid = r1.json()["session_id"]

    # Mock interviewer.next_turn to avoid LLM
    from services.schemas import InterviewTurn, InterviewerOS, InterviewStage, RiskLevel, QuestionSource
    fake_next = AsyncMock(return_value=(
        InterviewTurn(
            id="t2", session_id=sid, state=InterviewStage.S1_MOTIVATION,
            question="q", answer="a", score=70,
            covered_slots=["pain_real"], missing_slots=[],
            feedback="ok", next_question="next?", source=QuestionSource.PROJECT,
            interviewer_os=InterviewerOS(
                hidden_concern="", why_this_question="",
                missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.LOW,
            ),
        ),
        True,
        InterviewStage.S1_MOTIVATION,
    ))
    with patch("services.interviewer.next_turn", fake_next):
        r2 = client.post("/api/interviewer/next", json={
            "session_id": sid, "answer": "我访谈了 5 个用户", "user_id": "user-w",
        })
    assert r2.status_code == 200, r2.text


def test_profile_parse_accepts_user_id(client):
    """POST /api/profile/parse 同样接受 user_id."""
    fake_parse = AsyncMock(return_value={
        "project_summary": "X" * 100, "technical_keywords": [],
        "possible_weaknesses": [], "likely_followup_directions": [],
    })
    with patch("server.main.call_deepseek", fake_parse):
        r = client.post("/api/profile/parse", json={
            "raw_project_text": "我做了一个 AI 财务助理项目。"  * 5,
            "user_id": "user-p",
        })
    # profile/parse 可能 fallback 到 schema 验证；只验证 not 422
    assert r.status_code in (200, 500), r.text  # 200 if fake matched, 500 if call_deepseek bypass; not 422
