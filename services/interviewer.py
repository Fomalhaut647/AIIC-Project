"""Interviewer agent — 模拟面试官。state machine + LLM-driven 追问。"""
import uuid

from services.llm import call_deepseek
from services.prompts import INTERVIEWER_SYSTEM, INTERVIEWER_REPLAY_PROMPT_INJECT
from services.schemas import (
    InterviewStage, InterviewSession, InterviewTurn,
    InterviewerOS, InterviewPacket, QuestionSource, RiskLevel, UserModel,
    _canon_slot,
)
from services.question_bank import QuestionBank
from services.store import SessionStore


REQUIRED_SLOTS: dict[InterviewStage, list[str]] = {
    InterviewStage.S1_MOTIVATION: [
        "why_do", "target_user", "pain_real", "timing", "direction_relevance",
    ],
    InterviewStage.S2_OVERVIEW: [
        "goal", "io", "architecture", "user_flow", "personal_contribution",
    ],
    InterviewStage.S3_TECHNICAL: [
        "tech_solution", "method_choice_reason", "key_modules",
        "alternatives", "engineering_details",
    ],
    InterviewStage.S4_VALIDATION: [
        "baseline", "metric", "data_source", "evaluation_method",
        "control_experiment", "error_analysis",
    ],
    InterviewStage.S5_REFLECTION: [
        "failure_case", "edge_condition", "current_limit",
        "risk_control", "improvement",
    ],
    InterviewStage.S6_MATCHING: [
        "match_to_target", "future_direction", "personal_growth", "fit_reason",
    ],
}

# 推进规则常量
SLOT_COVERAGE_THRESHOLD = 0.8
VAGUE_SCORE_THRESHOLD = 40
VAGUE_DEGRADE_COUNT = 3

# 状态推进顺序
_STAGE_ORDER = [
    InterviewStage.S1_MOTIVATION, InterviewStage.S2_OVERVIEW,
    InterviewStage.S3_TECHNICAL, InterviewStage.S4_VALIDATION,
    InterviewStage.S5_REFLECTION, InterviewStage.S6_MATCHING,
    InterviewStage.DONE,
]


def next_stage(current: InterviewStage) -> InterviewStage:
    idx = _STAGE_ORDER.index(current)
    return _STAGE_ORDER[idx + 1] if idx + 1 < len(_STAGE_ORDER) else InterviewStage.DONE


def should_advance(session: InterviewSession, latest_turn: InterviewTurn) -> bool:
    required = set(REQUIRED_SLOTS[session.state])
    if not required:
        return True
    # 必须计入 latest_turn.covered_slots —— 在 next_turn 中本函数被调用时
    # latest_turn 尚未 append 进 session.turns（append_turn 在 should_advance 之后），
    # 否则一个回答即使覆盖全部 required slots 也无法触发当轮推进，coverage 永远 lag 一轮。
    covered_in_state: set[str] = set()
    if latest_turn.state == session.state:
        covered_in_state.update(latest_turn.covered_slots)
    for t in session.turns:
        if t.state == session.state:
            covered_in_state.update(t.covered_slots)
    coverage = len(covered_in_state & required) / len(required)
    return coverage >= SLOT_COVERAGE_THRESHOLD


def is_vague(turn: InterviewTurn) -> bool:
    return turn.score < VAGUE_SCORE_THRESHOLD


def update_vague_counter(session: InterviewSession, latest_turn: InterviewTurn) -> None:
    if is_vague(latest_turn):
        session.consecutive_vague_count += 1
    else:
        session.consecutive_vague_count = 0


def _target_role_phrase(target_value: str) -> str:
    return {
        "保研": "AI 方向高校实验室复试老师",
        "求职": "大厂 AI 团队的 hiring manager",
        "混合": "复试老师 + hiring manager 混合视角",
    }.get(target_value, "面试官")


async def start(
    packet: InterviewPacket,
    user_model: UserModel,
    bank: QuestionBank,
    store: SessionStore,
) -> tuple[str, InterviewTurn]:
    session_id = store.create(packet, user_model)
    state = InterviewStage.S1_MOTIVATION

    # 优先题库选 S1 开场题
    card = bank.query(target=packet.target, state=state, project_tags=[])
    if card is not None:
        question = card.question
        source = QuestionSource.BANK
    else:
        # 现场生成 S1 开场题
        question = await _generate_first_question(packet, user_model)
        source = QuestionSource.PROJECT

    first_turn = InterviewTurn(
        id=uuid.uuid4().hex,
        session_id=session_id,
        state=state,
        question=question,
        answer="",
        score=0,
        covered_slots=[],
        missing_slots=[],
        feedback="",
        next_question="",
        source=source,
        interviewer_os=InterviewerOS(
            hidden_concern="第一问要打开局面，看候选人是否真懂动机。",
            why_this_question="动机是项目说服力的根基。",
            missing_slots=[], what_i_want_to_hear=["真实痛点举例", "目标用户描述"],
            risk_level=RiskLevel.LOW,
        ),
    )
    # 持久化 first_turn 以便 next_turn 能找到 last_turn
    store.append_turn(session_id, first_turn)
    return session_id, first_turn


async def _generate_first_question(packet: InterviewPacket, user_model: UserModel) -> str:
    role = _target_role_phrase(packet.target.value)
    sys = (
        f"你是 {role}。基于项目摘要生成第一问，目的是了解项目动机。"
        f"\n\n项目摘要: {packet.project_summary}\n\n"
        "只输出问题本身，不要前缀，不要解释。"
    )
    if packet.replay_mode:
        sys += INTERVIEWER_REPLAY_PROMPT_INJECT.format(
            replay_focus_slots=", ".join(packet.replay_focus_slots),
            state="S1_motivation",
        )
    msgs = [
        {"role": "system", "content": sys},
        {"role": "user", "content": "请提出第一问。"},
    ]
    out = await call_deepseek(msgs, temperature=0.6)
    return out.strip().strip('"')


# ===== A11: next_turn + select_next_question =====
import json
from pydantic import BaseModel, Field

from services.prompts import (
    S6_BAOYAN_TEMPLATE, S6_QIUZHI_TEMPLATE, S6_HUNHE_TEMPLATE,
)


# Interviewer LLM 输出的 JSON schema（不含 id / session_id / state / source）
class _InterviewerOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    covered_slots: list[str]
    missing_slots: list[str]
    feedback: str
    next_question: str
    interviewer_os: InterviewerOS


def _s6_extra(target_value: str) -> str:
    return {
        "保研": S6_BAOYAN_TEMPLATE,
        "求职": S6_QIUZHI_TEMPLATE,
        "混合": S6_HUNHE_TEMPLATE,
    }.get(target_value, "")


async def next_turn(
    session_id: str,
    answer: str,
    bank: QuestionBank,
    store: SessionStore,
) -> tuple[InterviewTurn, bool, InterviewStage]:
    session = store.get(session_id)
    if not session.turns:
        raise ValueError("session has no turns; call start first")
    last_turn = session.turns[-1]

    # 1. 让 LLM 评估当前回答 + 给下一问草案
    llm_output = await _evaluate_and_suggest(session, last_turn, answer)

    # 2. 创建 turn（先以 LLM next_question 为草案，决策后可被 bank 覆盖）
    # 用户回答的题目 = 上一轮的 next_question；首轮回答时 next_question="" 退化为 last_turn.question
    asked_question = last_turn.next_question or last_turn.question
    new_turn = InterviewTurn(
        id=uuid.uuid4().hex,
        session_id=session_id,
        state=session.state,
        question=asked_question,
        answer=answer,
        score=llm_output.score,
        covered_slots=llm_output.covered_slots,
        missing_slots=llm_output.missing_slots,
        feedback=llm_output.feedback,
        next_question=llm_output.next_question,
        source=QuestionSource.PROJECT,
        interviewer_os=llm_output.interviewer_os,
    )

    # 3. 推进规则
    update_vague_counter(session, new_turn)
    advance = (
        should_advance_state(session.packet, new_turn)
        and should_advance(session, new_turn)
    )

    next_state = session.state
    if advance:
        next_state = next_stage(session.state)

    # 4. 选下一问 source
    if next_state == InterviewStage.DONE:
        new_turn.next_question = "（面试结束）"
        new_turn.source = QuestionSource.PROJECT
    elif advance:
        # 进入新 state，从题库选开场题
        card = bank.query(
            target=session.packet.target, state=next_state,
            project_tags=[], exclude_ids=session.used_question_ids,
        )
        if card is not None:
            new_turn.next_question = card.question
            new_turn.source = QuestionSource.BANK
            session.used_question_ids.append(card.id)
        # else: 用 LLM 草案 next_question，source=PROJECT
    elif session.consecutive_vague_count >= VAGUE_DEGRADE_COUNT:
        # 降级到基础概念
        new_turn.next_question = await _basic_concept_question(session)
        new_turn.source = QuestionSource.BASIC
        session.consecutive_vague_count = 0

    # 5. 持久化 + 推进 state
    store.append_turn(session_id, new_turn)
    session.state = next_state

    return new_turn, next_state != InterviewStage.DONE, next_state


async def _evaluate_and_suggest(
    session: InterviewSession,
    last_turn: InterviewTurn,
    answer: str,
) -> _InterviewerOutput:
    role = _target_role_phrase(session.packet.target.value)
    required = REQUIRED_SLOTS[session.state]
    turns_json = json.dumps([t.model_dump(mode="json") for t in session.turns],
                            ensure_ascii=False)
    extra = _s6_extra(session.packet.target.value) if session.state == InterviewStage.S6_MATCHING else ""
    sys_prompt = INTERVIEWER_SYSTEM.format(
        target_role=role,
        packet_json=session.packet.model_dump_json(),
        state=session.state.value,
        required_slots=", ".join(required),
        turns_json=turns_json,
    ) + ("\n\n" + extra if extra else "")
    if session.packet.replay_mode:
        sys_prompt += INTERVIEWER_REPLAY_PROMPT_INJECT.format(
            replay_focus_slots=", ".join(session.packet.replay_focus_slots),
            state=session.state.value,
        )
    user_msg = (
        f"上一题: {last_turn.question}\n用户回答: {answer}\n\n"
        "请按 schema 输出评估 + 下一问。"
    )
    fallback = _InterviewerOutput(
        score=50, covered_slots=[], missing_slots=required[:2],
        feedback="（系统评估异常，建议换个角度补充。）",
        next_question="能否再具体讲一下你的方案？",
        interviewer_os=InterviewerOS(
            hidden_concern="LLM 评估失败", why_this_question="降级问开放追问",
            missing_slots=required[:2], what_i_want_to_hear=[], risk_level=RiskLevel.LOW,
        ),
    )
    return await call_deepseek(
        [{"role": "system", "content": sys_prompt},
         {"role": "user", "content": user_msg}],
        response_schema=_InterviewerOutput,
        temperature=0.6, max_tokens=2500, fallback=fallback,
    )


async def _basic_concept_question(session: InterviewSession) -> str:
    msgs = [
        {"role": "system", "content": (
            f"你是 {_target_role_phrase(session.packet.target.value)}。"
            f"候选人连续回答空泛。请提一个与他项目相关的 AI 基础概念问题"
            f"（如 transformer / RAG / Agent / fine-tune 等的简单解释）。"
            f"\n项目摘要: {session.packet.project_summary}\n"
            "只输出问题本身。"
        )},
        {"role": "user", "content": "提一个基础概念追问。"},
    ]
    out = await call_deepseek(msgs, temperature=0.5, fallback="请用通俗的话解释一下你项目里用到的核心 AI 概念。")
    return out.strip().strip('"')


# ----------------- Plan2 P5: Replay mode (Spec D §7.2 / §7.3 / §7.6) -----------------

REPLAY_TURN_HARD_CAP = 8


def build_replay_packet(
    parent_packet: InterviewPacket,
    focus_slots: list[str],
    parent_session_id: str,
) -> InterviewPacket:
    """Spec D §7.2 — 从 parent packet 派生 replay packet。"""
    return parent_packet.model_copy(update={
        "replay_mode": True,
        "replay_focus_slots": list(focus_slots),
        "parent_session_id": parent_session_id,
    })


def should_advance_state(packet: InterviewPacket, latest_turn: InterviewTurn) -> bool:
    """Spec D §7.3 — Replay-mode short-circuit: replay 模式状态机一律不前进.

    NOTE: 这是一个 permission gate，独立于 v2 的 should_advance(session, turn)
    slot-coverage 判定。next_turn 内组合: advance = should_advance_state(...) and should_advance(...)
    """
    if packet.replay_mode:
        return False
    return True


def should_continue_replay(
    turns: list[InterviewTurn],
    focus_slots: list[str],
) -> bool:
    """Spec D §7.6 — replay session 是否继续.
    停止条件: (a) covered ⊇ focus，或 (b) turns >= 8 (hard cap)."""
    if len(turns) >= REPLAY_TURN_HARD_CAP:
        return False
    focus_canon = {_canon_slot(s) for s in focus_slots}
    covered: set[str] = set()
    for t in turns:
        for slot in t.covered_slots:
            covered.add(_canon_slot(slot))
    return not focus_canon.issubset(covered)
