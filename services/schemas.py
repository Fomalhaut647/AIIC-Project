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


class ResumeRewrite(BaseModel):
    original: str
    rewritten: str
    missing_evidence: list[str]


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
