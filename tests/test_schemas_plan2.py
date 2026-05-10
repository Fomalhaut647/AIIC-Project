"""Plan2 schemas tests — Spec D §5."""
from datetime import datetime

from services.schemas import (
    InterviewPacket,
    ReplayMiniReport,
    ResumeRevision,
    ResumeRewrite,
    SessionMeta,
    Target,
    UserProfile,
)


def test_session_meta_defaults():
    """SessionMeta minimal init works; non-required fields default."""
    meta = SessionMeta(
        session_id="s1",
        created_at=datetime(2026, 5, 12, 18, 30),
        target=Target.BAOYAN,
        project_summary_short="财会 Agent 项目",
    )
    assert meta.overall_score is None
    assert meta.weakness_tags == []
    assert meta.parent_session_id is None
    assert meta.is_replay is False


def test_user_profile_empty_init():
    """空 UserProfile 可构造（dashboard 空 state 用）。"""
    profile = UserProfile(user_id="anon", created_at=datetime.now())
    assert profile.total_sessions == 0
    assert profile.average_score is None
    assert profile.recurring_weaknesses == {}
    assert profile.projects == []
    assert profile.sessions == []


def test_user_profile_add_session_meta_aggregates():
    """add_session_meta 累计：sessions append + total +1 + average 重算 + weakness count + projects 去重。"""
    profile = UserProfile(user_id="anon", created_at=datetime.now())

    m1 = SessionMeta(
        session_id="s1",
        created_at=datetime(2026, 5, 12),
        target=Target.BAOYAN,
        project_summary_short="财会 Agent",
        overall_score=68,
        weakness_tags=["baseline", "错误分析"],
    )
    profile.add_session_meta(m1)

    assert profile.total_sessions == 1
    assert profile.average_score == 68.0
    assert profile.recurring_weaknesses == {"baseline": 1, "错误分析": 1}
    assert profile.projects == ["财会 Agent"]
    assert len(profile.sessions) == 1

    m2 = SessionMeta(
        session_id="s2",
        created_at=datetime(2026, 5, 13),
        target=Target.QIUZHI,
        project_summary_short="财会 Agent",  # 重复
        overall_score=82,
        weakness_tags=["baseline"],  # 重复 slot
    )
    profile.add_session_meta(m2)

    assert profile.total_sessions == 2
    assert profile.average_score == 75.0
    assert profile.recurring_weaknesses == {"baseline": 2, "错误分析": 1}
    assert profile.projects == ["财会 Agent"]  # 去重


def test_user_profile_canonicalizes_weakness():
    """weakness_tags 大小写/空白不同应当合并到同一 key。"""
    profile = UserProfile(user_id="anon", created_at=datetime.now())
    profile.add_session_meta(SessionMeta(
        session_id="s1", created_at=datetime.now(), target=Target.BAOYAN,
        project_summary_short="X", weakness_tags=["Baseline"],
    ))
    profile.add_session_meta(SessionMeta(
        session_id="s2", created_at=datetime.now(), target=Target.QIUZHI,
        project_summary_short="Y", weakness_tags=[" baseline "],
    ))
    assert profile.recurring_weaknesses == {"baseline": 2}


def test_interview_packet_replay_fields_default_off():
    """v2 现有 packet 构造不写 replay 字段也合法。"""
    pkt = InterviewPacket(
        target=Target.BAOYAN,
        interviewer_style="strict",
        project_summary="X",
        focus_slots=["baseline"],
    )
    assert pkt.replay_mode is False
    assert pkt.replay_focus_slots == []
    assert pkt.parent_session_id is None


def test_resume_rewrite_revision_history_default_empty():
    rr = ResumeRewrite(original="A", rewritten="B", missing_evidence=["x"])
    assert rr.revision_history == []


def test_resume_revision_required_fields():
    rev = ResumeRevision(
        iteration_index=1,
        timestamp=datetime.now(),
        user_text="改后版本",
        coach_feedback="不错",
        newly_covered=["baseline"],
        still_missing=[],
        is_good_enough=True,
    )
    assert rev.iteration_index == 1


def test_replay_mini_report_required_fields():
    r = ReplayMiniReport(
        parent_session_id="s1",
        replay_session_id="s2",
        focus_slots=["baseline"],
        coverage_before=0.33,
        coverage_after=0.80,
        delta_pp=47.0,
        sample_good_answer="...",
        next_step="继续盯 baseline",
    )
    assert r.delta_pp == 47.0
