"""Interviewer agent — 模拟面试官。state machine + LLM-driven 追问。"""
import uuid

from services.llm import call_deepseek
from services.prompts import INTERVIEWER_SYSTEM
from services.schemas import (
    InterviewStage, InterviewSession, InterviewTurn,
    InterviewerOS, InterviewPacket, QuestionSource, RiskLevel, UserModel,
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
    covered_in_state: set[str] = set()
    for t in session.turns:
        if t.state == session.state:
            covered_in_state.update(t.covered_slots)
    if not required:
        return True
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
    return session_id, first_turn


async def _generate_first_question(packet: InterviewPacket, user_model: UserModel) -> str:
    role = _target_role_phrase(packet.target.value)
    msgs = [
        {"role": "system", "content": (
            f"你是 {role}。基于项目摘要生成第一问，目的是了解项目动机。"
            f"\n\n项目摘要: {packet.project_summary}\n\n"
            "只输出问题本身，不要前缀，不要解释。"
        )},
        {"role": "user", "content": "请提出第一问。"},
    ]
    out = await call_deepseek(msgs, temperature=0.6)
    return out.strip().strip('"')
