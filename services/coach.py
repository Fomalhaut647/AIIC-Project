"""Coach agent — 训练组长。三个能力: onboard / plan / review。
Plan2 P3 追加：compute_replay_coverage + summarize_replay (Spec D §7.4 / §7.5)。
Plan2 P4 追加：iterate_resume (Spec D §8)。"""
from datetime import datetime

from pydantic import BaseModel, Field

from services.llm import call_deepseek
from services.prompts import (
    COACH_ONBOARD_SYSTEM, COACH_PLAN_SYSTEM, COACH_REVIEW_SYSTEM,
)
from services.schemas import (
    UserModel, InterviewPacket, InterviewTurn,
    OnboardResult, CoachPlanResult, EvaluationReport,
    Target, TrainingMode, RiskLevel,
    TrainingPlan, TrainingStep,
    ReplayMiniReport, ResumeRevision, SessionMeta, _canon_slot,
)


def _escape_braces(s: str) -> str:
    """转义 literal `{...}` 防止 str.format() 把它当占位符触发 KeyError。

    Plan2 P3/P4 共用：summarize_replay (turns_text) 与 iterate_resume
    (original / prior_missing items / user_revised) 都要先过这一步，
    否则用户内容含 `{xxx}` 就会静默 fallback。
    """
    return s.replace("{", "{{").replace("}", "}}")


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
    # str.format() 把 `{x}` 当占位符。若用户回答里出现 literal `{...}`，未转义会触发
    # KeyError → 静默走 except 分支（LLM 都没被调用过）。这里转义一次更稳。
    turns_text_safe = _escape_braces(turns_text)
    focus_human = ", ".join(focus_slots)

    prompt = _SUMMARIZE_REPLAY_PROMPT.format(
        focus_slots=focus_human,
        coverage_before=coverage_before,
        coverage_after=coverage_after,
        turns_text=turns_text_safe,
    )

    try:
        result: _ReplaySummaryLLM = await call_deepseek(
            messages=[{"role": "user", "content": prompt}],
            response_schema=_ReplaySummaryLLM,
            temperature=0.5,
            max_tokens=600,
        )
        sample = result.sample_good_answer or "未抓到亮眼回答"
        next_step = result.next_step or f"继续围绕 {focus_human} 多举具体例子"
    except Exception:
        # 不用 call_deepseek(fallback=...)：fallback 是静态值，但这里需要动态算
        # coverage_after / delta_pp，所以走自己的 try/except 让降级文案能引用 focus_slots。
        sample = "（无法摘录，请回看原文）"
        next_step = f"继续围绕 {focus_human} 多举具体例子"

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


# ----------------- Plan2 P4: Resume iterate (Spec D §8) -----------------


class _IterateResumeLLM(BaseModel):
    """Internal LLM response schema for iterate_resume (Spec D §8.2)。"""
    newly_covered: list[str] = Field(default_factory=list)
    still_missing: list[str] = Field(default_factory=list)
    coach_feedback: str = ""


_ITERATE_RESUME_PROMPT = """\
你是用户的简历教练。用户上一轮已收到 missing_evidence 清单，下面是新版本：

[原始 resume]
{original}

[上一轮 missing_evidence]
{prior_missing}

[用户改后的 resume]
{user_revised}

请评估：
- newly_covered: 上一轮 missing_evidence 中本次新版**确实**补到的条目（必须能在新版找到对应表述，不要凭空）
- still_missing: 仍未补到 / 写得太空泛的条目（沿用原描述，不要重新措辞）
- coach_feedback: 一段中文反馈，指出哪里做得好、哪里仍需具体化，落到具体动作

要求：newly_covered 与 still_missing 的并集应为上一轮 missing_evidence 的子集，不要新增之外的条目。
"""


async def iterate_resume(
    original: str,
    prior_missing: list[str],
    user_revised: str,
    iteration_index: int,
) -> ResumeRevision:
    """Spec D §8 — 用户提交新版 resume，LLM 评估覆盖度并给反馈。

    - still_missing 为空 → is_good_enough=True（结束迭代）
    - LLM 失败 → fallback 保守认为未覆盖（still_missing = prior_missing）
    """
    prompt = _ITERATE_RESUME_PROMPT.format(
        original=_escape_braces(original),
        prior_missing="\n".join(f"- {_escape_braces(m)}" for m in prior_missing),
        user_revised=_escape_braces(user_revised),
    )

    try:
        result: _IterateResumeLLM = await call_deepseek(
            messages=[{"role": "user", "content": prompt}],
            response_schema=_IterateResumeLLM,
            temperature=0.5,
            max_tokens=800,
        )
        # 防 LLM 幻觉：丢弃不在 prior_missing 中的项；找回 LLM 漏报的项 → 进 still。
        # 这样 newly ∪ still 在 prior_missing 内（不含幻觉），且 prior_missing 全被
        # 分入 newly 或 still（不漏报）。
        prior_set = set(prior_missing)
        raw_newly = [x for x in result.newly_covered if x in prior_set]
        raw_still = [x for x in result.still_missing if x in prior_set]
        accounted = set(raw_newly) | set(raw_still)
        # 优先尊重 newly 判定；漏报的 prior 项默认进 still。
        forgotten = [x for x in prior_missing if x not in accounted]
        newly = raw_newly
        still = raw_still + forgotten
        feedback = result.coach_feedback or "（暂无具体反馈）"

        # 退化情况：prior_missing 非空但 LLM 既没认下任何 newly 也没认下任何 still
        # （filter 后两侧都空）。说明 LLM 没看懂 / 全是幻觉。当作降级，避免 false
        # is_good_enough=True 让用户以为「过关」。
        if prior_missing and not raw_newly and not raw_still:
            still = list(prior_missing)
            feedback = "Coach 未能给出有效评估。请检查修改是否覆盖了上一轮的反馈，或稍后重试。"
    except Exception:
        # Fallback：保守认为本轮没覆盖任何条目，让用户决定是否继续。
        newly = []
        still = list(prior_missing)
        feedback = "LLM 暂时无响应，未能评估本轮修改。请稍后重试，或继续补充。"

    return ResumeRevision(
        iteration_index=iteration_index,
        timestamp=datetime.now(),
        user_text=user_revised,
        coach_feedback=feedback,
        newly_covered=newly,
        still_missing=still,
        is_good_enough=(len(still) == 0),
    )
