"""Coach iterate_resume tests — Spec D §8."""
from unittest.mock import AsyncMock, patch

import pytest

from services.coach import iterate_resume, _IterateResumeLLM
from services.schemas import ResumeRevision


@pytest.mark.asyncio
async def test_iterate_resume_partial_cover():
    """LLM 返回部分覆盖 → still_missing 非空 → is_good_enough=False。"""
    fake = AsyncMock(return_value=_IterateResumeLLM(
        newly_covered=["baseline"],
        still_missing=["错误分析的具体 case"],
        coach_feedback="baseline 部分讲清了，但错误 case 还需补充。",
    ))

    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="原始 resume",
            prior_missing=["baseline", "错误分析的具体 case"],
            user_revised="改后 resume",
            iteration_index=1,
        )

    assert isinstance(rev, ResumeRevision)
    assert rev.iteration_index == 1
    assert rev.newly_covered == ["baseline"]
    assert rev.still_missing == ["错误分析的具体 case"]
    assert rev.is_good_enough is False
    assert rev.user_text == "改后 resume"
    assert "baseline" in rev.coach_feedback


@pytest.mark.asyncio
async def test_iterate_resume_fully_covered():
    """still_missing 空 → is_good_enough=True。"""
    fake = AsyncMock(return_value=_IterateResumeLLM(
        newly_covered=["baseline", "错误分析"],
        still_missing=[],
        coach_feedback="都补到了，差不多可以。",
    ))

    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="原始", prior_missing=["baseline", "错误分析"],
            user_revised="改后", iteration_index=2,
        )

    assert rev.is_good_enough is True
    assert rev.still_missing == []


@pytest.mark.asyncio
async def test_iterate_resume_llm_failure_fallback():
    """LLM 抛 → 返回 fallback ResumeRevision，不挂。"""
    fake = AsyncMock(side_effect=RuntimeError("api down"))
    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="o", prior_missing=["x"], user_revised="r", iteration_index=1,
        )
    # fallback：still_missing 沿用 prior_missing；is_good_enough=False；feedback 写明 LLM 失败
    assert rev.still_missing == ["x"]
    assert rev.is_good_enough is False
    assert rev.iteration_index == 1


@pytest.mark.asyncio
async def test_iterate_resume_user_text_with_braces_does_not_break_format():
    """回归保护：user_revised / original / prior_missing 含 literal `{...}`
    时 str.format() 不应抛 KeyError 静默 fallback。"""
    fake = AsyncMock(return_value=_IterateResumeLLM(
        newly_covered=["baseline"],
        still_missing=[],
        coach_feedback="ok",
    ))
    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="原文里写了 {baseline_metric} 占位",
            prior_missing=["baseline {数据}", "其它"],
            user_revised="改后里也保留了 {baseline_metric} = 0.7",
            iteration_index=1,
        )
    # LLM 应当真的被调用过，不是 KeyError 走 fallback
    assert fake.await_count == 1
    assert rev.coach_feedback == "ok"
