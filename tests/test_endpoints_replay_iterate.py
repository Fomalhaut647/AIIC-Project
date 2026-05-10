"""Plan2 replay + resume_iterate endpoints — Spec D §6.1 / §7 / §8."""
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


def _make_parent_session(client, sid_marker: str = "parent") -> str:
    """Seed a real parent session via store.create + manual append + persist."""
    from services.schemas import (
        InterviewPacket, UserModel, Target, InterviewTurn, InterviewStage,
        InterviewerOS, RiskLevel,
    )
    store = client.app.state.store
    pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="P", focus_slots=["baseline"], replay_mode=False,
    )
    um = UserModel(id="u1", goal="保研", target=Target.BAOYAN)
    sid = store.create(pkt, um)
    session = store.get(sid)
    # Add one turn that did NOT cover baseline
    turn = InterviewTurn(
        id="t1", session_id=sid, state=InterviewStage.S4_VALIDATION,
        question="baseline?", answer="我没做", score=20,
        covered_slots=[], missing_slots=["baseline"],
        feedback="", next_question="", source="project",
        interviewer_os=InterviewerOS(
            hidden_concern="", why_this_question="",
            missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.HIGH,
        ),
    )
    session.turns.append(turn)
    store.persist(session)
    return sid


def _make_replay_session(client, parent_sid: str) -> str:
    """Seed a real replay session that COVERED baseline (so coverage_after = 1.0)."""
    from services.schemas import (
        InterviewPacket, UserModel, Target, InterviewTurn, InterviewStage,
        InterviewerOS, RiskLevel,
    )
    store = client.app.state.store
    pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="P", focus_slots=["baseline"],
        replay_mode=True, replay_focus_slots=["baseline"],
        parent_session_id=parent_sid,
    )
    um = UserModel(id="u1", goal="保研", target=Target.BAOYAN)
    sid = store.create(pkt, um)
    session = store.get(sid)
    turn = InterviewTurn(
        id="rt1", session_id=sid, state=InterviewStage.S4_VALIDATION,
        question="baseline?", answer="我用 zero-shot 作 baseline", score=80,
        covered_slots=["baseline"], missing_slots=[],
        feedback="", next_question="", source="project",
        interviewer_os=InterviewerOS(
            hidden_concern="", why_this_question="",
            missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.LOW,
        ),
    )
    session.turns.append(turn)
    store.persist(session)
    return sid


def _make_reviewed_session(client, missing_evidence: list[str]) -> str:
    """Seed a session WITH evaluation_report so /resume_iterate can find it."""
    from services.schemas import (
        InterviewPacket, UserModel, Target, EvaluationReport, ResumeRewrite,
        Evidence, HumorCard, TrainingPlan, TrainingStep, TrainingMode,
    )
    store = client.app.state.store
    pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="P", focus_slots=["baseline"],
    )
    um = UserModel(id="u1", goal="保研", target=Target.BAOYAN)
    sid = store.create(pkt, um)
    session = store.get(sid)
    session.evaluation_report = EvaluationReport(
        overall_score=70, summary="OK",
        strengths=[], weaknesses=[],
        evidence=[Evidence(quote="q", problem="p", suggestion="s")],
        dangerous_questions=["d1", "d2"],
        resume_rewrite=ResumeRewrite(
            original="A", rewritten="B",
            missing_evidence=missing_evidence,
            revision_history=[],
        ),
        next_training_plan=TrainingPlan(
            recommended_next_step=TrainingMode.NORMAL, reason="r",
            steps=[
                TrainingStep(name="a", goal="g", why_now="w"),
                TrainingStep(name="b", goal="g", why_now="w"),
            ],
        ),
        humor_card=HumorCard(title="T", content="C"),
    )
    store.persist(session)
    return sid


# ===== /api/interviewer/replay =====

def test_replay_404_for_unknown_parent(client):
    r = client.post("/api/interviewer/replay", json={
        "parent_session_id": "ghost-sid",
        "focus_slots": ["baseline"],
    })
    assert r.status_code == 404


def test_replay_starts_new_session(client):
    """Happy path: real parent → fork replay packet → new session id returned."""
    from services.schemas import InterviewTurn, InterviewerOS, RiskLevel, InterviewStage
    parent_sid = _make_parent_session(client)

    fake_first_turn = InterviewTurn(
        id="ft1", session_id="should-be-overridden",
        state=InterviewStage.S4_VALIDATION,
        question="重新讲讲 baseline？", answer="", score=0,
        covered_slots=[], missing_slots=[],
        feedback="", next_question="", source="project",
        interviewer_os=InterviewerOS(
            hidden_concern="", why_this_question="",
            missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.MEDIUM,
        ),
    )
    fake_start = AsyncMock(return_value=("replay-sid-mock", fake_first_turn))
    with patch("server.main.interviewer_start", fake_start):
        r = client.post("/api/interviewer/replay", json={
            "parent_session_id": parent_sid,
            "focus_slots": ["baseline"],
            "user_id": "u1",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == "replay-sid-mock"
    assert "baseline" in body["question"]
    # Verify build_replay_packet was wired through: fake_start should have been
    # called with a packet whose replay_mode=True and replay_focus_slots=["baseline"]
    args, kwargs = fake_start.await_args
    # Either positional or keyword; tolerate both
    packet = args[0] if args else kwargs.get("packet")
    assert packet.replay_mode is True
    assert packet.replay_focus_slots == ["baseline"]
    assert packet.parent_session_id == parent_sid


def test_replay_400_when_focus_slots_empty(client):
    """build_replay_packet raises ValueError on empty focus_slots → 400."""
    parent_sid = _make_parent_session(client)
    r = client.post("/api/interviewer/replay", json={
        "parent_session_id": parent_sid,
        "focus_slots": [],
    })
    assert r.status_code == 400


# ===== /api/interviewer/replay/finish =====

def test_replay_finish_404_for_missing_session(client):
    r = client.post("/api/interviewer/replay/finish", json={
        "session_id": "ghost-sid",
    })
    assert r.status_code == 404


def test_replay_finish_400_when_session_not_replay(client):
    """对非 replay session 调 /replay/finish → 400."""
    parent_sid = _make_parent_session(client)
    r = client.post("/api/interviewer/replay/finish", json={
        "session_id": parent_sid,
    })
    assert r.status_code == 400


def test_replay_finish_returns_mini_report(client):
    """合法 replay session → ReplayMiniReport JSON."""
    from services.schemas import ReplayMiniReport
    parent_sid = _make_parent_session(client)
    replay_sid = _make_replay_session(client, parent_sid)

    fake_summarize = AsyncMock(return_value=ReplayMiniReport(
        parent_session_id=parent_sid,
        replay_session_id=replay_sid,
        focus_slots=["baseline"],
        coverage_before=0.0,
        coverage_after=1.0,
        delta_pp=100.0,
        sample_good_answer="zero-shot 作 baseline",
        next_step="继续盯 evaluation",
    ))
    with patch("server.main.summarize_replay", fake_summarize):
        r = client.post("/api/interviewer/replay/finish", json={
            "session_id": replay_sid,
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delta_pp"] == 100.0
    assert "zero-shot" in body["sample_good_answer"]
    assert body["parent_session_id"] == parent_sid


# ===== /api/coach/resume_iterate =====

def test_resume_iterate_404_when_session_missing(client):
    r = client.post("/api/coach/resume_iterate", json={
        "session_id": "ghost-sid",
        "user_revised_resume": "...",
    })
    assert r.status_code == 404


def test_resume_iterate_409_when_no_review(client):
    """session 存在但未 review → 409."""
    parent_sid = _make_parent_session(client)
    r = client.post("/api/coach/resume_iterate", json={
        "session_id": parent_sid,
        "user_revised_resume": "改后",
    })
    assert r.status_code == 409


def test_resume_iterate_returns_revision_and_persists(client):
    """Happy path: 返回 ResumeRevision + 写回 session.evaluation_report.resume_rewrite."""
    from services.schemas import ResumeRevision
    sid = _make_reviewed_session(client, missing_evidence=["baseline"])

    fake_iter = AsyncMock(return_value=ResumeRevision(
        iteration_index=1,
        timestamp=datetime.now(),
        user_text="我加了 baseline 描述",
        coach_feedback="改对了",
        newly_covered=["baseline"],
        still_missing=[],
        is_good_enough=True,
    ))
    with patch("server.main.iterate_resume", fake_iter):
        r = client.post("/api/coach/resume_iterate", json={
            "session_id": sid,
            "user_revised_resume": "我加了 baseline 描述",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_good_enough"] is True
    assert body["iteration_index"] == 1

    # Verify persistence: re-load session JSON, revision_history should have 1 entry
    store = client.app.state.store
    session = store.get(sid)
    rh = session.evaluation_report.resume_rewrite.revision_history
    assert len(rh) == 1
    assert rh[0].iteration_index == 1
    assert session.evaluation_report.resume_rewrite.missing_evidence == []


def test_resume_iterate_iteration_index_increments(client):
    """连续两次 iterate → iteration_index = 1, 2."""
    from services.schemas import ResumeRevision
    sid = _make_reviewed_session(client, missing_evidence=["baseline", "评估"])

    # Round 1: covers baseline, still missing 评估
    rev1 = ResumeRevision(
        iteration_index=1, timestamp=datetime.now(),
        user_text="改后 1", coach_feedback="进步",
        newly_covered=["baseline"], still_missing=["评估"],
        is_good_enough=False,
    )
    fake_iter = AsyncMock(return_value=rev1)
    with patch("server.main.iterate_resume", fake_iter):
        r1 = client.post("/api/coach/resume_iterate", json={
            "session_id": sid, "user_revised_resume": "改后 1",
        })
    assert r1.status_code == 200
    assert r1.json()["iteration_index"] == 1

    # Round 2: should compute iteration_index=2 from history; LLM mocked again
    rev2 = ResumeRevision(
        iteration_index=2, timestamp=datetime.now(),
        user_text="改后 2", coach_feedback="完美",
        newly_covered=["评估"], still_missing=[],
        is_good_enough=True,
    )
    fake_iter2 = AsyncMock(return_value=rev2)
    with patch("server.main.iterate_resume", fake_iter2):
        r2 = client.post("/api/coach/resume_iterate", json={
            "session_id": sid, "user_revised_resume": "改后 2",
        })
    assert r2.status_code == 200
    assert r2.json()["iteration_index"] == 2

    # Verify: handler PASSED iteration_index=2 to iterate_resume
    args, kwargs = fake_iter2.await_args
    assert kwargs.get("iteration_index") == 2 or (args and args[3] == 2)
