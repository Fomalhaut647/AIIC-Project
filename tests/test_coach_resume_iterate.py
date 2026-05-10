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
        newly_covered=["baseline {数据}"],
        still_missing=["其它"],
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
    assert rev.newly_covered == ["baseline {数据}"]
    assert rev.still_missing == ["其它"]


@pytest.mark.asyncio
async def test_iterate_resume_filters_hallucinated_items():
    """Spec D §8.2 partition: LLM 幻觉返回不在 prior_missing 中的项 → 应被丢弃。
    同时漏报的 prior 项应自动归到 still（不能让 is_good_enough 假阳性）。"""
    fake = AsyncMock(return_value=_IterateResumeLLM(
        newly_covered=["baseline", "幻觉项 A"],   # 「幻觉项 A」不在 prior_missing
        still_missing=["幻觉项 B"],                # 「幻觉项 B」也不在
        coach_feedback="评估完成",
    ))
    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="o", prior_missing=["baseline", "错误分析"],
            user_revised="r", iteration_index=3,
        )
    # 幻觉被过滤
    assert "幻觉项 A" not in rev.newly_covered
    assert "幻觉项 B" not in rev.still_missing
    # baseline 被认下；错误分析 LLM 漏报 → 自动进 still
    assert rev.newly_covered == ["baseline"]
    assert rev.still_missing == ["错误分析"]
    assert rev.is_good_enough is False


@pytest.mark.asyncio
async def test_iterate_resume_all_empty_response_treated_as_degraded():
    """边界：prior_missing 非空，但 LLM 既没认下任何项也没列出任何 still
    （filter 后两侧都空）→ 应当降级，不能 is_good_enough 假阳性。"""
    fake = AsyncMock(return_value=_IterateResumeLLM(
        newly_covered=[],
        still_missing=[],
        coach_feedback="（无）",
    ))
    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="o", prior_missing=["baseline"],
            user_revised="r", iteration_index=4,
        )
    assert rev.is_good_enough is False
    assert rev.still_missing == ["baseline"]
    # feedback 提示用户检查或重试，不能维持「（无）」让用户以为通过
    assert "未能" in rev.coach_feedback or "重试" in rev.coach_feedback


@pytest.mark.asyncio
async def test_iterate_resume_empty_prior_missing_is_already_good_enough():
    """边界：prior_missing 本来就是空（用户已无 missing 项），LLM 即使全空也合法。
    退化保护只对 prior_missing 非空时生效。"""
    fake = AsyncMock(return_value=_IterateResumeLLM(
        newly_covered=[], still_missing=[], coach_feedback="已经很好",
    ))
    with patch("services.coach.call_deepseek", fake):
        rev = await iterate_resume(
            original="o", prior_missing=[],
            user_revised="r", iteration_index=5,
        )
    assert rev.is_good_enough is True
    assert rev.still_missing == []
    assert rev.coach_feedback == "已经很好"
