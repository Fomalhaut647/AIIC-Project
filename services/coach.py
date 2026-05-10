"""Coach agent — 训练组长。三个能力: onboard / plan / review."""
from services.llm import call_deepseek
from services.prompts import (
    COACH_ONBOARD_SYSTEM, COACH_PLAN_SYSTEM, COACH_REVIEW_SYSTEM,
)
from services.schemas import (
    UserModel, InterviewPacket, InterviewTurn,
    OnboardResult, CoachPlanResult, EvaluationReport,
    Target, TrainingMode, RiskLevel,
    TrainingPlan, TrainingStep,
)


_ONBOARD_FALLBACK = OnboardResult(
    need_more_info=True,
    followup_questions=["我没能理解你的需求。可以告诉我你这次主要是为了准备保研还是 AI 岗位面试吗？"],
)


async def onboard(user_message: str, history: list[dict] | None = None) -> OnboardResult:
    history = history or []
    messages = [
        {"role": "system", "content": COACH_ONBOARD_SYSTEM},
        *history,
        {"role": "user", "content": user_message},
    ]
    return await call_deepseek(
        messages, response_schema=OnboardResult,
        temperature=0.5, fallback=_ONBOARD_FALLBACK,
    )
