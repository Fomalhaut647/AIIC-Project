import pytest
from pathlib import Path
from services.schemas import (
    Target, RiskLevel, InterviewStage, QuestionSource,
    UserModel, InterviewPacket, InterviewTurn, InterviewerOS,
)
from services.store import SessionStore, SessionNotFound


@pytest.fixture
def packet():
    return InterviewPacket(
        target=Target.BAOYAN,
        interviewer_style="技术老师",
        project_summary="财会 Agent",
        focus_slots=["baseline"],
    )


@pytest.fixture
def user():
    return UserModel(id="u1", goal="保研", target=Target.BAOYAN)


def test_create_returns_session_id(tmp_path, packet, user):
    store = SessionStore(dump_dir=tmp_path)
    sid = store.create(packet, user)
    assert isinstance(sid, str) and len(sid) >= 16


def test_get_existing_session(tmp_path, packet, user):
    store = SessionStore(dump_dir=tmp_path)
    sid = store.create(packet, user)
    s = store.get(sid)
    assert s.session_id == sid
    assert s.packet.target == Target.BAOYAN


def test_get_missing_raises(tmp_path):
    store = SessionStore(dump_dir=tmp_path)
    with pytest.raises(SessionNotFound):
        store.get("nonexistent")


def test_append_turn_persists(tmp_path, packet, user):
    store = SessionStore(dump_dir=tmp_path)
    sid = store.create(packet, user)
    turn = InterviewTurn(
        id="t1", session_id=sid, state=InterviewStage.S1_MOTIVATION,
        question="q", answer="a", score=70, covered_slots=["pain_real"],
        missing_slots=[], feedback="f", next_question="nq",
        source=QuestionSource.PROJECT,
        interviewer_os=InterviewerOS(
            hidden_concern="x", why_this_question="y",
            missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.LOW,
        ),
    )
    store.append_turn(sid, turn)
    s = store.get(sid)
    assert len(s.turns) == 1
    # 验证 dump 文件存在
    assert (tmp_path / f"{sid}.json").exists()
