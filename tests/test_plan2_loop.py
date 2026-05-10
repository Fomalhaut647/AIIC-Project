"""Plan2 full integration smoke — Spec D §11.3.

完整链路：onboard → plan → start (demo) → next×2 → review → resume_iterate
       → replay → /interviewer/next → replay/finish → export.md → profile

所有 LLM 调用 mock；只验证 API 路由 + 数据流串联 + 持久化副作用。
不真打 LLM，不需要 DEEPSEEK_API_KEY。
"""
from __future__ import annotations

import json
from datetime import datetime
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


def _onboard_result_dict() -> dict:
    return {
        "need_more_info": False,
        "followup_questions": [],
        "user_model": {
            "id": "smoke-u",
            "goal": "保研",
            "target": "保研",
        },
        "recommended_packet": None,
    }


def _plan_result_dict() -> dict:
    return {
        "training_plan": {
            "recommended_next_step": "普通项目面",
            "reason": "覆盖完整 6 状态",
            "steps": [
                {"name": "S1 动机", "goal": "讲清", "why_now": "热身"},
                {"name": "S4 实验", "goal": "覆盖 baseline", "why_now": "评分要点"},
            ],
        },
        "interview_packet": {
            "target": "保研",
            "interviewer_style": "strict",
            "project_summary": "测试项目",
            "focus_slots": ["baseline"],
        },
    }


def _evaluation_report_dict() -> dict:
    return {
        "overall_score": 72,
        "summary": "整体讲清了愿景但缺 baseline 数字。",
        "strengths": ["项目动机清晰"],
        "weaknesses": ["baseline", "错误分析"],
        "evidence": [
            {"quote": "我用 zero-shot", "problem": "无对比", "suggestion": "加 random baseline"},
        ],
        "dangerous_questions": [
            "如何证明你的方案比 random baseline 好？",
            "错误案例你看了几个？",
        ],
        "resume_rewrite": {
            "original": "我做了一个 AI 财会助理...",
            "rewritten": "我设计并实现了 AI 财会助理...",
            "missing_evidence": ["baseline 对比", "错误 case 占比"],
            "revision_history": [],
        },
        "next_training_plan": {
            "recommended_next_step": "薄弱项重练",
            "reason": "baseline 必须补",
            "steps": [
                {"name": "重练 baseline", "goal": "覆盖", "why_now": "评分要点"},
                {"name": "看错误 case", "goal": "举 3 个例", "why_now": "细节"},
            ],
        },
        "humor_card": {"title": "缺 baseline", "content": "你的项目缺一个 baseline 才算完整。"},
    }


def _make_interview_turn(sid: str, covered: list[str], score: int = 70) -> dict:
    """For mocked interviewer.next_turn return value."""
    return {
        "id": "t-mock",
        "session_id": sid,
        "state": "S4_validation",
        "question": "baseline?",
        "answer": "我用 zero-shot",
        "score": score,
        "covered_slots": covered,
        "missing_slots": [],
        "feedback": "OK",
        "next_question": "下一题",
        "source": "project",
        "interviewer_os": {
            "hidden_concern": "",
            "why_this_question": "",
            "missing_slots": [],
            "what_i_want_to_hear": [],
            "risk_level": "中",
        },
    }


def test_plan2_full_loop_smoke(client, tmp_path: Path):
    """跑完所有 Plan2 endpoint 的 happy path; 验证持久化文件 + profile 累计。

    覆盖步骤 (Spec D §11.3):
      1. POST /api/coach/onboard      [mock]
      2. POST /api/coach/plan         [mock]
      3. POST /api/interviewer/start  (demo 模式, 不需 mock)
      4. POST /api/coach/review       [mock] → user_profile 落盘 + session.evaluation_report
      5. POST /api/coach/resume_iterate [mock] → revision_history append
      6. GET  /api/sessions/{sid}/export.md → 200 + text/markdown
      7. POST /api/interviewer/replay → fork session
      8. POST /api/interviewer/replay/finish [mock] → mini-report
      9. GET  /api/users/{user_id}/profile → total_sessions=1（review 写过）
    """
    from services.schemas import (
        OnboardResult, CoachPlanResult, EvaluationReport, ResumeRevision,
        ReplayMiniReport, InterviewTurn, InterviewStage,
    )

    user_id = "smoke-user-001"

    # --- 1. onboard ---
    onboard_mock = AsyncMock(return_value=OnboardResult.model_validate(_onboard_result_dict()))
    with patch("server.main.coach_onboard", onboard_mock):
        r = client.post("/api/coach/onboard", json={
            "user_message": "我准备保研, 项目 AI 财会助理",
            "history": [],
            "user_id": user_id,
        })
    assert r.status_code == 200, r.text

    # --- 2. plan ---
    plan_mock = AsyncMock(return_value=CoachPlanResult.model_validate(_plan_result_dict()))
    with patch("server.main.coach_plan", plan_mock):
        r = client.post("/api/coach/plan", json={
            "user_model": {"id": "smoke-u", "goal": "保研", "target": "保研"},
            "project_summary": "AI 财会助理项目",
            "user_id": user_id,
        })
    assert r.status_code == 200, r.text

    # --- 3. interviewer/start (demo bypasses LLM) ---
    r = client.post("/api/interviewer/start?demo=true", json={
        "interview_packet": _plan_result_dict()["interview_packet"],
        "user_model": {"id": "smoke-u", "goal": "保研", "target": "保研"},
        "user_id": user_id,
    })
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert sid

    # Force the session into DONE state to bypass review's 400 (state≠DONE & turns<6).
    store = client.app.state.store
    store.get(sid).state = InterviewStage.DONE

    # --- 4. coach/review (mock LLM) ---
    review_mock = AsyncMock(return_value=EvaluationReport.model_validate(_evaluation_report_dict()))
    with patch("server.main.coach_review", review_mock):
        r = client.post("/api/coach/review", json={
            "session_id": sid, "user_id": user_id,
        })
    assert r.status_code == 200, r.text
    report_body = r.json()
    assert report_body["overall_score"] == 72
    assert "baseline" in report_body["weaknesses"]

    # Side effect: user profile JSON should now exist
    profile_path = tmp_path / "users" / f"{user_id}.json"
    assert profile_path.exists(), f"review hook should write profile; ls={list(tmp_path.iterdir())}"
    profile_data = json.loads(profile_path.read_text())
    assert profile_data["user_id"] == user_id
    assert profile_data["total_sessions"] == 1
    # weakness canonicalization (lowercase + strip)
    assert profile_data["recurring_weaknesses"].get("baseline") == 1

    # Side effect: session JSON now contains evaluation_report
    session_path = tmp_path / "sessions" / f"{sid}.json"
    assert session_path.exists()
    session_data = json.loads(session_path.read_text())
    assert session_data["evaluation_report"] is not None

    # --- 5. coach/resume_iterate (mock LLM) ---
    resume_mock = AsyncMock(return_value=ResumeRevision(
        iteration_index=1,
        timestamp=datetime.now(),
        user_text="我加了 baseline 对比表",
        coach_feedback="改对了 baseline 部分",
        newly_covered=["baseline 对比"],
        still_missing=["错误 case 占比"],
        is_good_enough=False,
    ))
    with patch("server.main.iterate_resume", resume_mock):
        r = client.post("/api/coach/resume_iterate", json={
            "session_id": sid,
            "user_revised_resume": "我加了 baseline 对比表",
            "user_id": user_id,
        })
    assert r.status_code == 200, r.text
    rev = r.json()
    assert rev["iteration_index"] == 1
    assert rev["is_good_enough"] is False
    # Side effect: session JSON revision_history grew
    session_data2 = json.loads(session_path.read_text())
    assert len(session_data2["evaluation_report"]["resume_rewrite"]["revision_history"]) == 1

    # --- 6. export.md ---
    r = client.get(f"/api/sessions/{sid}/export.md")
    assert r.status_code == 200, r.text
    assert "text/markdown" in r.headers["content-type"]
    assert "ProjectProbe 复盘报告" in r.text
    # All 8 sections + interviewer_os branch + revision_history rendered
    for i in range(1, 9):
        assert f"## {i}." in r.text, f"sec {i} missing"
    assert "改对了 baseline 部分" in r.text  # revision history coach_feedback

    # --- 7. interviewer/replay ---
    fake_first_turn = InterviewTurn.model_validate(
        _make_interview_turn("__will_be_replaced__", covered=[])
    )
    fake_replay_start = AsyncMock(return_value=("replay-sid-mock", fake_first_turn))
    with patch("server.main.interviewer_start", fake_replay_start):
        r = client.post("/api/interviewer/replay", json={
            "parent_session_id": sid,
            "focus_slots": ["baseline"],
            "user_id": user_id,
        })
    assert r.status_code == 200, r.text
    replay_body = r.json()
    assert replay_body["session_id"] == "replay-sid-mock"

    # --- 8. interviewer/replay/finish (mock summarize_replay) ---
    # Need a real replay session on disk; replay-sid-mock is fictional. Build one
    # via store.create and persist with replay packet.
    from services.schemas import InterviewPacket, UserModel, Target, InterviewerOS, RiskLevel
    real_replay_pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="AI 财会助理项目", focus_slots=["baseline"],
        replay_mode=True, replay_focus_slots=["baseline"],
        parent_session_id=sid,
    )
    real_um = UserModel(id="smoke-u", goal="保研", target=Target.BAOYAN)
    real_replay_sid = store.create(real_replay_pkt, real_um)
    # Add one turn that covered baseline
    rep_session = store.get(real_replay_sid)
    real_turn = InterviewTurn(
        id="rt1", session_id=real_replay_sid, state=InterviewStage.S4_VALIDATION,
        question="baseline?", answer="我加了 random baseline 0.65 vs my 0.78",
        score=85, covered_slots=["baseline"], missing_slots=[],
        feedback="ok", next_question="", source="project",
        interviewer_os=InterviewerOS(
            hidden_concern="", why_this_question="",
            missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.LOW,
        ),
    )
    rep_session.turns.append(real_turn)
    store.persist(rep_session)

    summarize_mock = AsyncMock(return_value=ReplayMiniReport(
        parent_session_id=sid,
        replay_session_id=real_replay_sid,
        focus_slots=["baseline"],
        coverage_before=0.0,
        coverage_after=1.0,
        delta_pp=100.0,
        sample_good_answer="我加了 random baseline 0.65 vs my 0.78",
        next_step="继续盯 evaluation 部分",
    ))
    with patch("server.main.summarize_replay", summarize_mock):
        r = client.post("/api/interviewer/replay/finish", json={
            "session_id": real_replay_sid,
            "user_id": user_id,
        })
    assert r.status_code == 200, r.text
    mini = r.json()
    assert mini["delta_pp"] == 100.0
    assert "random baseline" in mini["sample_good_answer"]

    # --- 9. profile aggregator endpoint ---
    r = client.get(f"/api/users/{user_id}/profile")
    assert r.status_code == 200
    profile_resp = r.json()
    assert profile_resp["total_sessions"] >= 1
    assert profile_resp["recurring_weaknesses"].get("baseline") == 1
    # project_summary_short comes from session.packet.project_summary (truncated to 80)
    # which the demo /start handler set to "测试项目" (per _plan_result_dict above).
    assert profile_resp["projects"][0].startswith("测试项目")


def test_plan2_anonymous_user_default(client):
    """user_id 缺省时 fallback 到 "anonymous"; 各 endpoint 不报 422."""
    from services.schemas import OnboardResult
    onboard_mock = AsyncMock(return_value=OnboardResult(
        need_more_info=True, followup_questions=["更多?"],
    ))
    with patch("server.main.coach_onboard", onboard_mock):
        r = client.post("/api/coach/onboard", json={
            "user_message": "X",
            "history": [],
            # 故意不传 user_id
        })
    assert r.status_code == 200, r.text


def test_plan2_baseline_v2_endpoints_unaffected(client):
    """sanity: 不传 user_id 的 v2 老调用方式应继续工作 (Plan2 只加可选字段)."""
    r = client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "commit_hash" in body
