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


_PLAN_FALLBACK = CoachPlanResult(
    training_plan=TrainingPlan(
        recommended_next_step=TrainingMode.NORMAL,
        reason="LLM 输出异常，回退到默认普通项目面。",
        steps=[
            TrainingStep(name="项目陈述", goal="把项目讲完整", why_now="主线优先"),
            TrainingStep(name="项目深挖", goal="覆盖 baseline / 实验 / 失败反思",
                         why_now="为复试 / 面试做准备"),
        ],
    ),
    interview_packet=InterviewPacket(
        target=Target.HUNHE,
        interviewer_style="资深技术老师",
        intensity=RiskLevel.MEDIUM,
        project_summary="（待用户补充）",
        focus_slots=["personal_contribution", "baseline", "failure_case"],
    ),
)


async def plan(user_model: UserModel, project_summary: str) -> CoachPlanResult:
    messages = [
        {"role": "system", "content": COACH_PLAN_SYSTEM.format(
            user_model_json=user_model.model_dump_json(),
            project_summary=project_summary,
        )},
        {"role": "user", "content": "请生成 CoachPlanResult JSON。"},
    ]
    return await call_deepseek(
        messages, response_schema=CoachPlanResult,
        temperature=0.5, fallback=_PLAN_FALLBACK,
    )
