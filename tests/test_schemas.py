"""Smoke tests for services/schemas.py — 验证关键字段约束。"""
import pytest
from pydantic import ValidationError
from services.schemas import (
    Target, InterviewStage, RiskLevel,
    UserModel, InterviewTurn, InterviewerOS, EvaluationReport,
    Evidence, ResumeRewrite, TrainingPlan, TrainingStep, HumorCard,
)


def test_user_model_minimal():
    u = UserModel(id="abc", goal="保研", target=Target.BAOYAN)
    assert u.preferred_style.value == "直接"


def test_user_model_target_enum():
    with pytest.raises(ValidationError):
        UserModel(id="x", goal="g", target="美团")  # 非 enum 值


def test_interview_turn_score_bounds():
    base_kwargs = dict(
        id="t1", session_id="s1", state=InterviewStage.S1_MOTIVATION,
        question="q", answer="a", covered_slots=[], missing_slots=[],
        feedback="f", next_question="nq", source="project",
        interviewer_os=InterviewerOS(
            hidden_concern="x", why_this_question="y",
            missing_slots=[], what_i_want_to_hear=[],
            risk_level=RiskLevel.LOW,
        ),
    )
    InterviewTurn(score=50, **base_kwargs)
    with pytest.raises(ValidationError):
        InterviewTurn(score=101, **base_kwargs)
    with pytest.raises(ValidationError):
        InterviewTurn(score=-1, **base_kwargs)


def test_training_plan_min_steps():
    with pytest.raises(ValidationError):
        TrainingPlan(
            recommended_next_step="普通项目面",
            reason="r",
            steps=[TrainingStep(name="s1", goal="g", why_now="w")],  # 仅 1 个，需 ≥2
        )


def test_evaluation_report_dangerous_questions_bounds():
    base = dict(
        overall_score=60, summary="s", strengths=[], weaknesses=[],
        evidence=[Evidence(quote="q", problem="p", suggestion="s")],
        resume_rewrite=ResumeRewrite(original="o", rewritten="r", missing_evidence=[]),
        next_training_plan=TrainingPlan(
            recommended_next_step="普通项目面", reason="r",
            steps=[
                TrainingStep(name="s1", goal="g", why_now="w"),
                TrainingStep(name="s2", goal="g", why_now="w"),
            ],
        ),
        humor_card=HumorCard(title="t", content="c"),
    )
    EvaluationReport(dangerous_questions=["q1", "q2"], **base)  # min ok
    with pytest.raises(ValidationError):
        EvaluationReport(dangerous_questions=["q1"], **base)  # < 2 fail
