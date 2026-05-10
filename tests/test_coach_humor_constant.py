"""Plan3.5 Imp 5 — humor_card 由后端固定模板注入,不再交给 LLM。

要保护:
1. coach.review() 即便 LLM 返回任意 humor_card,最终输出也是 _HUMOR_CARD_CONSTANT
2. fallback 路径(LLM 异常)同样返回 _HUMOR_CARD_CONSTANT
3. EvaluationReport schema humor_card 已转 Optional[HumorCard], 默认 None 仍合法
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.coach import _HUMOR_CARD_CONSTANT, review
from services.schemas import (
    EvaluationReport, Evidence, HumorCard, InterviewPacket, ResumeRewrite,
    RiskLevel, Target, TrainingPlan, TrainingStep, UserModel,
)


def _minimal_packet() -> InterviewPacket:
    return InterviewPacket(
        target=Target.QIUZHI,
        interviewer_style="资深技术老师",
        intensity=RiskLevel.MEDIUM,
        project_summary="测试项目",
        focus_slots=["pain_real"],
    )


def _minimal_user_model() -> UserModel:
    return UserModel(id="u1", goal="求职", target=Target.QIUZHI)


def _minimal_plan() -> TrainingPlan:
    return TrainingPlan(
        recommended_next_step="普通项目面",
        reason="r",
        steps=[
            TrainingStep(name="s1", goal="g1", why_now="w1"),
            TrainingStep(name="s2", goal="g2", why_now="w2"),
        ],
    )


def _llm_report_with_garbage_humor() -> EvaluationReport:
    """LLM mock: 返一个 humor_card,但内容是 LLM 凭空编的差笑话。
    review() 应该把它覆盖成 _HUMOR_CARD_CONSTANT。"""
    return EvaluationReport(
        overall_score=80,
        summary="还行",
        strengths=["架构清晰"],
        weaknesses=["缺 baseline"],
        evidence=[Evidence(quote="q", problem="p", suggestion="s")],
        dangerous_questions=["d1", "d2"],
        resume_rewrite=ResumeRewrite(original="o", rewritten="r"),
        next_training_plan=_minimal_plan(),
        humor_card=HumorCard(title="LLM 编的", content="不好笑的笑话"),
    )


@pytest.mark.asyncio
async def test_review_overrides_llm_humor_with_constant() -> None:
    """LLM 即便返了 humor_card,review() 应注入 _HUMOR_CARD_CONSTANT 覆盖。"""
    fake_llm = AsyncMock(return_value=_llm_report_with_garbage_humor())
    with patch("services.coach.call_deepseek", fake_llm):
        result = await review(
            user_model=_minimal_user_model(),
            packet=_minimal_packet(),
            turns=[],
        )
    assert result.humor_card == _HUMOR_CARD_CONSTANT
    assert result.humor_card.title == "高价值 bug：薄弱项是真痛点"
    assert "1.01^30" in result.humor_card.content
    assert "1.2^2" in result.humor_card.content


@pytest.mark.asyncio
async def test_review_fallback_path_uses_constant() -> None:
    """call_deepseek 抛异常 → 走 fallback；fallback humor_card 应是常量。

    实际 call_deepseek 内部捕获异常返 fallback；这里直接 mock 抛异常会绕过它,
    所以我们模拟 call_deepseek 真实行为：传入的 fallback 被原样返。"""

    def _return_fallback(*args, **kwargs):
        # 模拟 call_deepseek 的 fallback 路径行为
        return kwargs["fallback"]

    fake_llm = AsyncMock(side_effect=_return_fallback)
    with patch("services.coach.call_deepseek", fake_llm):
        result = await review(
            user_model=_minimal_user_model(),
            packet=_minimal_packet(),
            turns=[],
        )
    # 即便走 fallback 路径,review() 末尾仍统一覆盖一次,确保 humor_card == 常量
    assert result.humor_card == _HUMOR_CARD_CONSTANT


def test_evaluation_report_humor_card_optional() -> None:
    """schema 改 humor_card: HumorCard | None = None 后,不传入也合法。"""
    rpt = EvaluationReport(
        overall_score=70,
        summary="s",
        strengths=[], weaknesses=[],
        evidence=[Evidence(quote="q", problem="p", suggestion="s")],
        dangerous_questions=["d1", "d2"],
        resume_rewrite=ResumeRewrite(original="o", rewritten="r"),
        next_training_plan=_minimal_plan(),
        # humor_card 故意不传, schema 默认 None
    )
    assert rpt.humor_card is None
