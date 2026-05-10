"""Coach agent — 训练组长。三个能力: onboard / plan / review。
Plan2 P3 追加：compute_replay_coverage + summarize_replay (Spec D §7.4 / §7.5)。"""
from pydantic import BaseModel

from services.llm import call_deepseek
from services.prompts import (
    COACH_ONBOARD_SYSTEM, COACH_PLAN_SYSTEM, COACH_REVIEW_SYSTEM,
)
from services.schemas import (
    UserModel, InterviewPacket, InterviewTurn,
    OnboardResult, CoachPlanResult, EvaluationReport,
    Target, TrainingMode, RiskLevel,
    TrainingPlan, TrainingStep,
    ReplayMiniReport, SessionMeta, _canon_slot,
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


async def review(
    user_model: UserModel,
    packet: InterviewPacket,
    turns: list[InterviewTurn],
) -> EvaluationReport:
    turns_json = "[" + ",".join(t.model_dump_json() for t in turns) + "]"
    messages = [
        {"role": "system", "content": COACH_REVIEW_SYSTEM.format(
            user_model_json=user_model.model_dump_json(),
            packet_json=packet.model_dump_json(),
            turns_json=turns_json,
        )},
        {"role": "user", "content": "请生成 EvaluationReport JSON。"},
    ]
    # review 是 demo 关键路径，给一个最小 fallback 避免崩溃
    from services.schemas import (
        Evidence, ResumeRewrite, HumorCard,
    )
    fallback = EvaluationReport(
        overall_score=0,
        summary="系统繁忙，请稍后重试或重新开始训练。",
        strengths=[], weaknesses=["LLM 暂时无响应"],
        evidence=[Evidence(quote="（无）", problem="系统降级", suggestion="重试")],
        dangerous_questions=["（无）", "（无）"],
        resume_rewrite=ResumeRewrite(original="", rewritten="", missing_evidence=[]),
        next_training_plan=_PLAN_FALLBACK.training_plan,
        humor_card=HumorCard(title="系统也会打盹", content="再试一次。"),
    )
    return await call_deepseek(
        messages, response_schema=EvaluationReport,
        temperature=0.7, max_tokens=4000, fallback=fallback,
    )


# ----------------- Plan2 P3: Replay helpers (Spec D §7.4 / §7.5) -----------------


class _ReplaySummaryLLM(BaseModel):
    """Internal LLM response schema for summarize_replay (Spec D §7.5)。"""
    sample_good_answer: str
    next_step: str


def compute_replay_coverage(turns: list[InterviewTurn], focus_slots: list[str]) -> float:
    """Spec D §7.4 — focus_slots 中被 turns.covered_slots 覆盖的占比。

    - canonicalize: lowercase + strip（对齐 _canon_slot）
    - 空 focus_slots → 0.0（不抛 ZeroDivisionError）
    """
    if not focus_slots:
        return 0.0
    focus_canon = {_canon_slot(s) for s in focus_slots}
    covered: set[str] = set()
    for turn in turns:
        for slot in turn.covered_slots:
            covered.add(_canon_slot(slot))
    return len(focus_canon & covered) / len(focus_canon)


_SUMMARIZE_REPLAY_PROMPT = """\
你是用户的训练教练。用户刚完成「重练」session，仅围绕以下槽位深挖：
focus_slots: {focus_slots}
原 session 在该槽位的覆盖度: {coverage_before:.2f}
本次重练完成后的覆盖度: {coverage_after:.2f}

下面是重练对话：
{turns_text}

要求：
- sample_good_answer 必须是用户原文的摘录或近似复述，不要凭空编造；如无亮眼回答写"未抓到亮眼回答"
- next_step 要落到具体动作，不要空泛"加油"
"""


async def summarize_replay(
    parent_meta: SessionMeta,
    replay_session_id: str,
    replay_turns: list[InterviewTurn],
    focus_slots: list[str],
    coverage_before: float,
) -> ReplayMiniReport:
    """Spec D §7.5 — LLM 生成 sample_good_answer + next_step；失败 fallback 默认文案。"""
    coverage_after = compute_replay_coverage(replay_turns, focus_slots)
    delta_pp = (coverage_after - coverage_before) * 100

    turns_text = "\n\n".join(
        f"Q: {t.question}\nA: {t.answer}" for t in replay_turns
    )

    prompt = _SUMMARIZE_REPLAY_PROMPT.format(
        focus_slots=", ".join(focus_slots),
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        turns_text=turns_text,
    )

    try:
        result: _ReplaySummaryLLM = await call_deepseek(
            messages=[{"role": "user", "content": prompt}],
            response_schema=_ReplaySummaryLLM,
            temperature=0.5,
            max_tokens=600,
        )
        sample = result.sample_good_answer or "未抓到亮眼回答"
        next_step = result.next_step or f"继续围绕 {focus_slots} 多举具体例子"
    except Exception:
        sample = "（无法摘录，请回看原文）"
        next_step = f"继续围绕 {', '.join(focus_slots)} 多举具体例子"

    return ReplayMiniReport(
        parent_session_id=parent_meta.session_id,
        replay_session_id=replay_session_id,
        focus_slots=focus_slots,
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        delta_pp=delta_pp,
        sample_good_answer=sample,
        next_step=next_step,
    )
