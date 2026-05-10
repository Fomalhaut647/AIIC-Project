"""Interviewer agent — 模拟面试官。state machine + LLM-driven 追问。"""
from services.schemas import (
    InterviewStage, InterviewSession, InterviewTurn,
)


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
