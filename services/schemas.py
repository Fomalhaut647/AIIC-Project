"""ProjectProbe v2 数据契约 — 所有 Pydantic 类型集中在此。"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class Target(str, Enum):
    BAOYAN = "保研"
    QIUZHI = "求职"
    HUNHE = "混合"


class InterviewStage(str, Enum):
    S1_MOTIVATION = "S1_motivation"
    S2_OVERVIEW = "S2_overview"
    S3_TECHNICAL = "S3_technical"
    S4_VALIDATION = "S4_validation"
    S5_REFLECTION = "S5_reflection"
    S6_MATCHING = "S6_matching"
    DONE = "done"


class RiskLevel(str, Enum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


class TrainingMode(str, Enum):
    NORMAL = "普通项目面"
    PRESSURE = "压力面"
    RESUME_FIX = "简历修改"
    WEAKNESS = "薄弱项重练"


class PreferredStyle(str, Enum):
    DIRECT = "直接"
    GENTLE = "温和"
    HUMOROUS = "幽默"


class QuestionSource(str, Enum):
    PROJECT = "project"
    BANK = "synthetic_question_bank"
    BASIC = "basic_concept"
    FALLBACK = "fallback"


class ProjectSummary(BaseModel):
    title: str
    one_liner: str = Field(max_length=80)
    technical_keywords: list[str] = []
    likely_followup_directions: list[str] = []


class UserModel(BaseModel):
    id: str
    goal: str
    target: Target
    target_program: str | None = None
    projects: list[ProjectSummary] = []
    strengths: list[str] = []
    recurring_weaknesses: list[str] = []
    resume_issues: list[str] = []
    preferred_style: PreferredStyle = PreferredStyle.DIRECT
    current_stage: TrainingMode = TrainingMode.NORMAL


class TrainingStep(BaseModel):
    name: str
    goal: str
    why_now: str


class TrainingPlan(BaseModel):
    recommended_next_step: TrainingMode
    reason: str
    steps: list[TrainingStep] = Field(min_length=2)


class InterviewPacket(BaseModel):
    target: Target
    interviewer_style: str
    intensity: RiskLevel = RiskLevel.MEDIUM
    project_summary: str
    focus_slots: list[str]
    constraints: list[str] = []
    question_policy: str = "项目优先 → 题库匹配 → 基础概念 → 八股兜底"
    # Plan2 新增（Spec D §5.3）
    replay_mode: bool = False
    replay_focus_slots: list[str] = Field(default_factory=list)
    parent_session_id: str | None = None


class InterviewerOS(BaseModel):
    hidden_concern: str
    why_this_question: str
    missing_slots: list[str]
    what_i_want_to_hear: list[str]
    risk_level: RiskLevel


class InterviewTurn(BaseModel):
    id: str
    session_id: str
    state: InterviewStage
    question: str
    answer: str
    score: int = Field(ge=0, le=100)
    covered_slots: list[str]
    missing_slots: list[str]
    feedback: str
    next_question: str
    source: QuestionSource
    interviewer_os: InterviewerOS


class Evidence(BaseModel):
    quote: str
    problem: str
    suggestion: str


class ResumeRevision(BaseModel):
    """Spec D §5.4 — 简历多轮迭代单条（Plan2 类型，定义在此以满足 ResumeRewrite 的前向引用；其余 Plan2 schemas 见文件末尾段）。"""
    iteration_index: int
    timestamp: datetime
    user_text: str
    coach_feedback: str
    newly_covered: list[str] = Field(default_factory=list)
    still_missing: list[str] = Field(default_factory=list)
    is_good_enough: bool = False


class ResumeRewrite(BaseModel):
    original: str
    rewritten: str
    missing_evidence: list[str] = Field(default_factory=list)
    # Plan2 新增（Spec D §5.4）
    revision_history: list[ResumeRevision] = Field(default_factory=list)


class HumorCard(BaseModel):
    title: str
    content: str


class EvaluationReport(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    evidence: list[Evidence] = Field(min_length=1)
    dangerous_questions: list[str] = Field(min_length=2, max_length=5)
    resume_rewrite: ResumeRewrite
    next_training_plan: TrainingPlan
    humor_card: HumorCard


class OnboardResult(BaseModel):
    need_more_info: bool
    followup_questions: list[str] = []
    user_model: UserModel | None = None
    recommended_packet: InterviewPacket | None = None


class CoachPlanResult(BaseModel):
    training_plan: TrainingPlan
    interview_packet: InterviewPacket


class QuestionCard(BaseModel):
    id: str
    category: str
    tags: list[str]
    applies_to: list[Target] = Field(min_length=1)
    related_state: InterviewStage
    trigger: str
    question: str
    followups: list[str] = Field(min_length=1, max_length=5)
    good_answer_points: list[str] = Field(min_length=2)
    red_flags: list[str] = Field(min_length=2)
    related_slots: list[str]
    difficulty: RiskLevel = RiskLevel.MEDIUM
    source: Literal["seed", "synthetic"] = "synthetic"
    generated_at: datetime | None = None
    reviewed: bool = False


class InterviewSession(BaseModel):
    session_id: str
    user_model: UserModel
    packet: InterviewPacket
    state: InterviewStage = InterviewStage.S1_MOTIVATION
    turns: list[InterviewTurn] = []
    consecutive_vague_count: int = 0
    used_question_ids: list[str] = []
    # Plan2 P8 / Spec D §9.1: report attached after /api/coach/review;
    # export.md gates 409 when this is None (implicit "reviewed" status).
    evaluation_report: EvaluationReport | None = None


# ----------------- Plan2 长期训练 -----------------

def _canon_slot(s: str) -> str:
    """Canonicalize slot name for cross-session counting (Spec D §7.4 / §11.1)."""
    return s.strip().lower()


class SessionMeta(BaseModel):
    """Spec D §5.1 — UserProfile 时间线一行。"""
    session_id: str
    created_at: datetime
    target: Target
    project_summary_short: str
    overall_score: int | None = None
    weakness_tags: list[str] = Field(default_factory=list)
    parent_session_id: str | None = None
    is_replay: bool = False


class UserProfile(BaseModel):
    """Spec D §5.2 — 个人主页聚合视图。"""
    user_id: str
    created_at: datetime
    sessions: list[SessionMeta] = Field(default_factory=list)
    total_sessions: int = 0
    average_score: float | None = None
    recurring_weaknesses: dict[str, int] = Field(default_factory=dict)
    projects: list[str] = Field(default_factory=list)

    def add_session_meta(self, meta: SessionMeta) -> None:
        """聚合：append + 重算 hero stats + 累计弱点 + 去重项目。"""
        self.sessions.append(meta)
        self.total_sessions = len(self.sessions)

        scored = [m.overall_score for m in self.sessions if m.overall_score is not None]
        self.average_score = sum(scored) / len(scored) if scored else None

        for tag in meta.weakness_tags:
            key = _canon_slot(tag)
            self.recurring_weaknesses[key] = self.recurring_weaknesses.get(key, 0) + 1

        if meta.project_summary_short and meta.project_summary_short not in self.projects:
            self.projects.append(meta.project_summary_short)


class ReplayMiniReport(BaseModel):
    """Spec D §5.5 — 重练结束的迷你报告。"""
    parent_session_id: str
    replay_session_id: str
    focus_slots: list[str]
    coverage_before: float
    coverage_after: float
    delta_pp: float
    sample_good_answer: str
    next_step: str
