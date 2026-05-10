"""Coach replay helpers tests — Spec D §7.4 / §7.5."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from services.coach import (
    compute_replay_coverage,
    summarize_replay,
    _ReplaySummaryLLM,
)
from services.schemas import (
    InterviewStage,
    InterviewTurn,
    ReplayMiniReport,
    SessionMeta,
    Target,
)


def _turn(covered: list[str]) -> InterviewTurn:
    """Test helper: only covered_slots matters; all other fields dummy."""
    return InterviewTurn(
        id="t",
        session_id="s",
        state=InterviewStage.S1_MOTIVATION,
        question="q",
        answer="a",
        score=0,
        covered_slots=covered,
        missing_slots=[],
        feedback="",
        next_question="",
        source="project",
        interviewer_os={
            "hidden_concern": "",
            "why_this_question": "",
            "missing_slots": [],
            "what_i_want_to_hear": [],
            "risk_level": "低",
        },
    )


def test_coverage_full_match():
    turns = [_turn(["baseline", "评估"]), _turn(["错误分析"])]
    focus = ["baseline", "评估", "错误分析"]
    assert compute_replay_coverage(turns, focus) == 1.0


def test_coverage_partial():
    turns = [_turn(["baseline"])]
    focus = ["baseline", "评估", "错误分析"]
    assert compute_replay_coverage(turns, focus) == pytest.approx(1 / 3, rel=1e-3)


def test_coverage_canonicalization():
    """大小写 + 空白不一致应被归一。"""
    turns = [_turn(["Baseline"])]
    focus = ["  baseline  "]
    assert compute_replay_coverage(turns, focus) == 1.0


def test_coverage_empty_focus_returns_zero():
    """空 focus_slots 不应触发 ZeroDivisionError。"""
    assert compute_replay_coverage([_turn(["x"])], []) == 0.0


def test_coverage_no_overlap():
    turns = [_turn(["unrelated"])]
    focus = ["baseline"]
    assert compute_replay_coverage(turns, focus) == 0.0


@pytest.mark.asyncio
async def test_summarize_replay_happy_path():
    """LLM 返回合法 _ReplaySummaryLLM → ReplayMiniReport 字段填齐。"""
    parent = SessionMeta(
        session_id="parent-1",
        created_at=datetime.now(),
        target=Target.BAOYAN,
        project_summary_short="财会",
    )
    turns = [_turn(["baseline"]), _turn(["baseline", "评估"])]
    focus = ["baseline", "评估"]

    fake_llm = AsyncMock(return_value=_ReplaySummaryLLM(
        sample_good_answer="我用最简单 zero-shot 作 baseline...",
        next_step="继续盯 baseline 的细节",
    ))

    with patch("services.coach.call_deepseek", fake_llm):
        report = await summarize_replay(
            parent_meta=parent,
            replay_session_id="replay-1",
            replay_turns=turns,
            focus_slots=focus,
            coverage_before=0.33,
        )

    assert isinstance(report, ReplayMiniReport)
    assert report.parent_session_id == "parent-1"
    assert report.replay_session_id == "replay-1"
    assert report.coverage_before == 0.33
    assert report.coverage_after == 1.0
    assert report.delta_pp == pytest.approx(67.0, abs=0.5)
    assert "zero-shot" in report.sample_good_answer


@pytest.mark.asyncio
async def test_summarize_replay_llm_failure_fallback():
    """LLM 抛异常 → fallback 默认文案，不抛错。"""
    parent = SessionMeta(
        session_id="parent-1",
        created_at=datetime.now(),
        target=Target.BAOYAN,
        project_summary_short="X",
    )
    fake_llm = AsyncMock(side_effect=RuntimeError("api down"))

    with patch("services.coach.call_deepseek", fake_llm):
        report = await summarize_replay(
            parent_meta=parent,
            replay_session_id="r1",
            replay_turns=[_turn(["baseline"])],
            focus_slots=["baseline"],
            coverage_before=0.0,
        )

    assert "无法摘录" in report.sample_good_answer or "回看原文" in report.sample_good_answer
    assert report.next_step  # 非空
    assert report.coverage_after == 1.0
