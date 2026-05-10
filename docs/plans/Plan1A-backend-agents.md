# AIIC v2 Plan1A — Backend Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 [Spec A](../specs/A-backend-agents.md) 全部 services/ 模块（Pydantic schemas / prompts / store / LLM 封装 / Coach / Interviewer），为 Plan1C 的 API 层提供可调用的业务函数。

**Architecture:** services/ 目录下 7 个 Python 模块，按依赖顺序：schemas → prompts → store → llm → question_bank（Plan1B 提供）→ coach → interviewer。Pydantic v2 + httpx async + python-dotenv。

**Tech Stack:** Python (Pixi) / Pydantic v2 / httpx / python-dotenv / pytest

**Pre-conditions:**
- main 上的 v1 业务代码（server/ web/ tests/ deploy/）将在 Task A0 删除
- `.env` 已含 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`
- Plan1B 与本 plan 可并行；coach/interviewer 实施时 question_bank 接口需已存在（可 stub 占位）

**Spec coverage:**

| Spec A 节 | Plan task |
|---|---|
| §1 模块边界 / 依赖图 | A0 |
| §2 数据契约 | A2 |
| §3 LLM 封装 + JSON repair | A5 |
| §4 Coach (onboard / plan / review) | A6, A7, A8 |
| §5 Interviewer (state machine, OS) | A9, A10, A11 |
| §6 Persistence | A4 |
| §7 错误处理与降级 | A5 (impl), A11 (verify) |
| §8 测试策略 | tests/ 散落于各 task |
| §9 实施顺序 | 任务编号即顺序 |

---

### Task A0: 清理 v1 业务代码 + 准备 v2 目录骨架

**Files:**
- Delete: `server/`, `web/`, `tests/`, `deploy/`
- Create: `services/__init__.py`, `tests/__init__.py`, `data/sessions/.gitkeep`, `logs/.gitkeep`, `scripts/__init__.py`

- [ ] **Step 1: 验证 .env 含 3 个 DEEPSEEK 变量**

```bash
grep -E "^DEEPSEEK_(API_KEY|BASE_URL|MODEL)=" .env | wc -l
```

Expected output: `3`

如果 < 3，停止并要求用户在 `.env` 补齐。

- [ ] **Step 2: 删除 v1 业务代码**

```bash
git rm -r server web tests deploy
```

- [ ] **Step 3: 创建 v2 目录骨架**

```bash
mkdir -p services tests data/sessions logs scripts
touch services/__init__.py tests/__init__.py scripts/__init__.py
touch data/sessions/.gitkeep logs/.gitkeep
```

- [ ] **Step 4: 验证 pixi.toml 复用依赖完整**

```bash
grep -E "^(fastapi|uvicorn|httpx|python-dotenv|pytest|pydantic)" pixi.toml
```

Expected: 至少 `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `pytest` 5 行。`pydantic` 是 fastapi 的传递依赖，可缺。

如缺 `pydantic`：`pixi add "pydantic>=2"`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: remove v1 business code and prepare v2 service skeleton

v1 (mimo web chat) 业务代码 (server/ web/ tests/ deploy/) 删除；保留
pixi.toml/pixi.lock/pytest.ini/.env/docs/ 等基础设施。新建 services/
tests/ data/sessions/ logs/ scripts/ 空目录为 v2 准备。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A1: 写 .gitignore 兜底

**Files:**
- Modify: `.gitignore` (确认 `data/sessions/*.json` `logs/*.log` 被忽略)

- [ ] **Step 1: 检查现状**

```bash
cat .gitignore | grep -E "(data/sessions|logs/)"
```

如果空输出 → 进 Step 2。

- [ ] **Step 2: 追加规则**

```bash
cat >> .gitignore <<'EOF'

# v2 runtime artifacts
data/sessions/*.json
logs/*.log
EOF
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore v2 runtime artifacts (sessions, llm logs)"
```

---

### Task A2: services/schemas.py — Pydantic 数据契约

**Files:**
- Create: `services/schemas.py`
- Test: `tests/test_schemas.py`

完整内容参 [Spec A §2](../specs/A-backend-agents.md#2-数据契约servicesschemaspy)。

- [ ] **Step 1: 写 services/schemas.py**

完整内容（按 Spec A §2.1 - §2.7）：

```python
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
```

- [ ] **Step 2: 写 tests/test_schemas.py**

```python
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
```

- [ ] **Step 3: Run tests**

```bash
pixi run pytest tests/test_schemas.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add services/schemas.py tests/test_schemas.py
git commit -m "feat(schemas): add pydantic data contracts for ProjectProbe v2"
```

---

### Task A3: services/prompts.py — LLM prompt 字面常量

**Files:**
- Create: `services/prompts.py`

只放 prompt 字符串常量，不含逻辑。完整 prompt skeleton 见 Spec A §4.1-4.3 与 §5.5-5.6。

- [ ] **Step 1: 写 services/prompts.py**

```python
"""所有 LLM prompt 字面常量。Coach 与 Interviewer 共享。"""

COACH_ONBOARD_SYSTEM = """\
你是 ProjectProbe 的训练组长 Coach。你的任务是了解用户的目标和需求，
最终生成 UserModel 和推荐的 InterviewPacket。

第一轮必问场景：用户准备的是「保研复试」「AI 岗位面试」还是「混合」。
如果用户的初始消息已明确表达，直接抽取，不要重复问。

完成下列任务后输出 OnboardResult JSON：
1. 抽取 target、target_program、preferred_style
2. 让用户简述项目（不需要详细，只要标题 + 一句话）
3. 让用户说出当前最害怕被追问的方向（用于 focus_slots）

如果信息不全：need_more_info=true + followup_questions（≤2 题，简短）。
如果信息够：need_more_info=false + 完整 user_model + recommended_packet。

不要替用户回答面试问题。不要给宏观训练计划（那是 plan 阶段的事）。
"""

COACH_PLAN_SYSTEM = """\
你是 ProjectProbe 的训练组长 Coach。基于以下信息生成训练计划：

UserModel:
{user_model_json}

ProjectSummary:
{project_summary}

输出 CoachPlanResult JSON：
1. TrainingPlan：
   - recommended_next_step: 普通项目面 / 压力面 / 简历修改 / 薄弱项重练
   - reason: 一句话
   - steps: ≥2 个 TrainingStep (name / goal / why_now)
2. InterviewPacket：
   - focus_slots 必须 target-aware：
     · 保研 → 偏 S1（项目动机）+ S6（研究匹配）+ S4（实验验证）
     · 求职 → 偏 S3（技术深挖）+ S4（实验验证）+ S5（失败反思）
     · 混合 → S3 + S4 + S6 各占一份
   - focus_slots ≤5 个（贪多 = 没重点）
"""

COACH_REVIEW_SYSTEM = """\
你是 ProjectProbe 的训练组长 Coach。面试已结束。基于完整 turns 生成 EvaluationReport JSON。

UserModel: {user_model_json}
InterviewPacket: {packet_json}
Turns: {turns_json}

要求：
1. evidence[].quote 必须是 turns 中真实出现的用户原话片段，不能改写
2. dangerous_questions 必须是 ≥2 个未来面试官最可能继续追问的题
3. resume_rewrite.rewritten 要把面试中暴露的真实细节纳入，不能凭空捏造
4. resume_rewrite.missing_evidence 列出改写后仍缺的证据点
5. next_training_plan 必须给 ≥2 个 TrainingStep
6. humor_card 规则（强约束）：
   - 必须引用本轮真实暴露的具体 missing_slot
   - 把它解释为「高价值 bug」/ 调试梗 / 数学梗 / 论文梗
   - 不允许「加油，你一定行」类空泛鸡汤
   - 结尾给一个具体的下一步动作
7. preferred_style 影响语气；但 humor_card 的幽默基调不可削减
"""

INTERVIEWER_SYSTEM = """\
你是 ProjectProbe 模拟面试官。你模拟的是第一次见到候选人的 {target_role}。

你只能看到：
- InterviewPacket: {packet_json}
- 当前 state: {state}
- required_slots（本 state）: {required_slots}
- 当前对话历史: {turns_json}

每次用户回答后，输出 JSON 含以下字段（除 id / session_id / state / source 由调用方填充）：
- score (0-100)：回答完整度（覆盖 required_slots 的程度）
- covered_slots: 用户回答覆盖了哪些 slot 名（从 required_slots 选）
- missing_slots: 哪些 required_slots 没覆盖
- feedback (≤80 字符)：给用户的简短点评，点明缺什么
- next_question: 下一问（优先针对 missing_slots，否则推进 state 后的开场题）
- interviewer_os:
  - hidden_concern: 你真正担心什么
  - why_this_question: 为什么追问
  - missing_slots: 与上面的 missing_slots 同步
  - what_i_want_to_hear: 优秀回答应包含什么
  - risk_level: 低 / 中 / 高

**禁忌**：
- 不要替用户回答
- 不要给宏观训练规划
- 不要安慰用户
- 不要看 user_model（你不知道用户长期画像）
- 不要输出完整 chain-of-thought：interviewer_os 是面向用户的判断摘要，不是你的内部推理
"""

S6_BAOYAN_TEMPLATE = """\
当前进入 S6（匹配与总结）。你的角色现在是某高校 AI 实验室的复试老师。
重点询问：研究方向匹配 / 未来研究计划 / 个人成长 / 为什么适合这个实验室。
"""

S6_QIUZHI_TEMPLATE = """\
当前进入 S6（匹配与总结）。你的角色现在是某团队的 hiring manager。
重点询问：岗位匹配 / 1 个月内能交付什么 / 团队需要但你没做过的部分 / 学习路径。
"""

S6_HUNHE_TEMPLATE = """\
当前进入 S6（匹配与总结）。前 2 题走保研模板（研究方向匹配 / 未来研究），
后 2 题走求职模板（岗位匹配 / 落地能力）。
"""

PROFILE_PARSE_SYSTEM = """\
你是项目材料解析器。从用户粘贴的项目原文中抽取结构化画像。

输出 JSON：
{
  "project_summary": "≤200 字概述",
  "technical_keywords": [...],
  "possible_weaknesses": [...],   # 哪些点容易被追问空泛
  "likely_followup_directions": [...]
}
"""

JSON_OUTPUT_INSTRUCTION = """\

**严格输出要求**：
- 只输出合法 JSON，不要带 Markdown 代码块包裹
- 字段必须严格符合下方 schema
- 不要输出任何解释文字、前缀、后缀
- 字符串值中的引号、换行需正确转义

JSON Schema:
{schema_json}
"""

JSON_REPAIR_INSTRUCTION = """\
你刚才的输出不是合法 JSON 或不符合 schema。
原始输出：
```
{original_output}
```
解析错误：
```
{error_message}
```
请只修复 JSON 格式 / schema 字段，不要改变字段语义，不要添加解释文字，不要输出 Markdown。
直接输出修正后的 JSON。
"""
```

- [ ] **Step 2: Smoke import**

```bash
pixi run python -c "from services.prompts import COACH_ONBOARD_SYSTEM; assert len(COACH_ONBOARD_SYSTEM) > 100; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/prompts.py
git commit -m "feat(prompts): add llm prompt constants for coach + interviewer"
```

---

### Task A4: services/store.py — SessionStore

**Files:**
- Create: `services/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: 写 tests/test_store.py（先写测试）**

```python
import pytest
from pathlib import Path
from services.schemas import (
    Target, RiskLevel, InterviewStage, QuestionSource,
    UserModel, InterviewPacket, InterviewTurn, InterviewerOS,
)
from services.store import SessionStore, SessionNotFound


@pytest.fixture
def packet():
    return InterviewPacket(
        target=Target.BAOYAN,
        interviewer_style="技术老师",
        project_summary="财会 Agent",
        focus_slots=["baseline"],
    )


@pytest.fixture
def user():
    return UserModel(id="u1", goal="保研", target=Target.BAOYAN)


def test_create_returns_session_id(tmp_path, packet, user):
    store = SessionStore(dump_dir=tmp_path)
    sid = store.create(packet, user)
    assert isinstance(sid, str) and len(sid) >= 16


def test_get_existing_session(tmp_path, packet, user):
    store = SessionStore(dump_dir=tmp_path)
    sid = store.create(packet, user)
    s = store.get(sid)
    assert s.session_id == sid
    assert s.packet.target == Target.BAOYAN


def test_get_missing_raises(tmp_path):
    store = SessionStore(dump_dir=tmp_path)
    with pytest.raises(SessionNotFound):
        store.get("nonexistent")


def test_append_turn_persists(tmp_path, packet, user):
    store = SessionStore(dump_dir=tmp_path)
    sid = store.create(packet, user)
    turn = InterviewTurn(
        id="t1", session_id=sid, state=InterviewStage.S1_MOTIVATION,
        question="q", answer="a", score=70, covered_slots=["pain_real"],
        missing_slots=[], feedback="f", next_question="nq",
        source=QuestionSource.PROJECT,
        interviewer_os=InterviewerOS(
            hidden_concern="x", why_this_question="y",
            missing_slots=[], what_i_want_to_hear=[], risk_level=RiskLevel.LOW,
        ),
    )
    store.append_turn(sid, turn)
    s = store.get(sid)
    assert len(s.turns) == 1
    # 验证 dump 文件存在
    assert (tmp_path / f"{sid}.json").exists()
```

- [ ] **Step 2: Run test → 应失败（SessionStore 不存在）**

```bash
pixi run pytest tests/test_store.py -v
```

Expected: ImportError on `from services.store import ...`.

- [ ] **Step 3: 写 services/store.py**

```python
"""In-memory session store with fire-and-forget JSON dump."""
from pathlib import Path
import uuid

from services.schemas import (
    InterviewPacket, InterviewSession, InterviewTurn, UserModel,
)


class SessionNotFound(KeyError):
    pass


class SessionStore:
    def __init__(self, dump_dir: Path = Path("data/sessions")):
        self._sessions: dict[str, InterviewSession] = {}
        self._dump_dir = Path(dump_dir)
        self._dump_dir.mkdir(parents=True, exist_ok=True)

    def create(self, packet: InterviewPacket, user_model: UserModel) -> str:
        sid = uuid.uuid4().hex
        self._sessions[sid] = InterviewSession(
            session_id=sid, user_model=user_model, packet=packet,
        )
        return sid

    def get(self, session_id: str) -> InterviewSession:
        if session_id not in self._sessions:
            raise SessionNotFound(session_id)
        return self._sessions[session_id]

    def append_turn(self, session_id: str, turn: InterviewTurn) -> None:
        session = self.get(session_id)
        session.turns.append(turn)
        self._dump(session)

    def _dump(self, session: InterviewSession) -> None:
        path = self._dump_dir / f"{session.session_id}.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test → 应通过**

```bash
pixi run pytest tests/test_store.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/store.py tests/test_store.py
git commit -m "feat(store): add in-memory SessionStore with fire-and-forget json dump"
```

---

### Task A5: services/llm.py — DeepSeek 封装 + JSON repair + fallback

**Files:**
- Create: `services/llm.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: 写 tests/test_llm.py（mock httpx）**

```python
import json
import pytest
from unittest.mock import patch, AsyncMock
from pydantic import BaseModel

from services.llm import call_deepseek, LLMSchemaError


class _DummyOut(BaseModel):
    name: str
    score: int


def _mock_response(content: str):
    """Build a fake httpx-like response with .json() returning OpenAI-style body."""
    resp = AsyncMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"choices": [{"message": {"content": content}}]}
    return resp


@pytest.mark.asyncio
async def test_call_returns_text_when_no_schema():
    with patch("services.llm._post_chat", new=AsyncMock(return_value=_mock_response("hello"))):
        out = await call_deepseek([{"role": "user", "content": "hi"}])
        assert out == "hello"


@pytest.mark.asyncio
async def test_call_parses_valid_json_into_schema():
    with patch("services.llm._post_chat", new=AsyncMock(
        return_value=_mock_response('{"name": "x", "score": 10}'),
    )):
        out = await call_deepseek(
            [{"role": "user", "content": "ok"}],
            response_schema=_DummyOut,
        )
        assert isinstance(out, _DummyOut)
        assert out.name == "x"


@pytest.mark.asyncio
async def test_repair_retry_then_success():
    bad = "this is not json"
    good = '{"name": "x", "score": 10}'
    with patch("services.llm._post_chat", new=AsyncMock(
        side_effect=[_mock_response(bad), _mock_response(good)],
    )) as m:
        out = await call_deepseek(
            [{"role": "user", "content": "ok"}],
            response_schema=_DummyOut,
        )
        assert isinstance(out, _DummyOut)
        assert m.await_count == 2


@pytest.mark.asyncio
async def test_repair_fails_returns_fallback():
    bad = "still not json"
    fallback = _DummyOut(name="fb", score=0)
    with patch("services.llm._post_chat", new=AsyncMock(
        side_effect=[_mock_response(bad), _mock_response(bad)],
    )):
        out = await call_deepseek(
            [{"role": "user", "content": "ok"}],
            response_schema=_DummyOut,
            fallback=fallback,
        )
        assert out == fallback


@pytest.mark.asyncio
async def test_repair_fails_no_fallback_raises():
    bad = "still not json"
    with patch("services.llm._post_chat", new=AsyncMock(
        side_effect=[_mock_response(bad), _mock_response(bad)],
    )):
        with pytest.raises(LLMSchemaError):
            await call_deepseek(
                [{"role": "user", "content": "ok"}],
                response_schema=_DummyOut,
            )
```

- [ ] **Step 2: 加 pytest-asyncio 依赖（如缺）**

```bash
pixi run python -c "import pytest_asyncio" 2>&1 | grep -q "ModuleNotFoundError" && pixi add pytest-asyncio || echo "already installed"
```

在 pytest.ini 或 pyproject.toml 加：
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Run test → 应失败**

```bash
pixi run pytest tests/test_llm.py -v
```

Expected: ImportError on `services.llm`.

- [ ] **Step 4: 写 services/llm.py**

```python
"""DeepSeek (OpenAI-compatible) async client with JSON repair + fallback."""
from __future__ import annotations
import json
import logging
import os
import time
from typing import TypeVar
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from services.prompts import JSON_OUTPUT_INSTRUCTION, JSON_REPAIR_INSTRUCTION

load_dotenv()

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

LOG_PATH = Path("logs/llm.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_logger = logging.getLogger("aiic.llm")
if not _logger.handlers:
    h = logging.FileHandler(LOG_PATH, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(h)
    _logger.setLevel(logging.INFO)

T = TypeVar("T", bound=BaseModel)


class LLMSchemaError(Exception):
    pass


async def _post_chat(messages, temperature, max_tokens, *, json_mode: bool = False):
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
               "Content-Type": "application/json"}
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                                 headers=headers, json=body)
        resp.raise_for_status()
        return resp


def _extract_content(resp) -> str:
    return resp.json()["choices"][0]["message"]["content"]


async def call_deepseek(
    messages: list[dict],
    *,
    response_schema: type[T] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    fallback: T | str | None = None,
) -> T | str:
    """See Spec A §3.1 for full contract."""
    started = time.time()
    msgs = [dict(m) for m in messages]
    role = msgs[0].get("content", "")[:40] if msgs else ""

    if response_schema is not None:
        # 注入 JSON 输出要求
        schema_json = json.dumps(response_schema.model_json_schema(), ensure_ascii=False)
        msgs[-1]["content"] = (msgs[-1]["content"]
                               + JSON_OUTPUT_INSTRUCTION.format(schema_json=schema_json))
        resp = await _post_chat(msgs, temperature, max_tokens, json_mode=True)
        content = _extract_content(resp)
        try:
            parsed = response_schema.model_validate_json(content)
            _log(role, len(content), False, False, started)
            return parsed
        except (json.JSONDecodeError, ValidationError) as e:
            # repair retry
            repair_msg = {
                "role": "user",
                "content": JSON_REPAIR_INSTRUCTION.format(
                    original_output=content, error_message=str(e),
                ),
            }
            resp2 = await _post_chat([*msgs, {"role": "assistant", "content": content},
                                      repair_msg], temperature, max_tokens, json_mode=True)
            content2 = _extract_content(resp2)
            try:
                parsed = response_schema.model_validate_json(content2)
                _log(role, len(content2), True, False, started)
                return parsed
            except (json.JSONDecodeError, ValidationError):
                if fallback is not None:
                    _log(role, len(content2), True, True, started)
                    return fallback
                raise LLMSchemaError(f"repair failed: {content2[:200]}")
    else:
        resp = await _post_chat(msgs, temperature, max_tokens, json_mode=False)
        content = _extract_content(resp)
        _log(role, len(content), False, False, started)
        return content


def _log(role: str, resp_chars: int, repair: bool, fallback: bool, started: float):
    duration_ms = int((time.time() - started) * 1000)
    _logger.info(
        f"role={role!r} | resp_chars={resp_chars} | repair={repair} "
        f"| fallback={fallback} | duration_ms={duration_ms}"
    )
```

- [ ] **Step 5: Run test → 应通过**

```bash
pixi run pytest tests/test_llm.py -v
```

Expected: 5 PASS.

- [ ] **Step 6: Smoke real LLM call**

```bash
pixi run python -c "
import asyncio
from services.llm import call_deepseek
out = asyncio.run(call_deepseek([{'role':'user','content':'回复 OK'}]))
print('LLM ok:', out[:50])
"
```

Expected: `LLM ok: OK` 或类似。

- [ ] **Step 7: Commit**

```bash
git add services/llm.py tests/test_llm.py pytest.ini pixi.toml pixi.lock
git commit -m "feat(llm): add deepseek async client with json repair retry + fallback"
```

---

### Task A6: services/coach.py — onboard

**Files:**
- Create: `services/coach.py`

P0 不写 Coach 端到端测试（依赖 LLM）。靠 smoke + 后续 e2e demo 验证。

- [ ] **Step 1: 写 services/coach.py（仅 onboard）**

```python
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
```

- [ ] **Step 2: Smoke**

```bash
pixi run python -c "
import asyncio
from services.coach import onboard
r = asyncio.run(onboard('我准备保研人工智能创新中心，项目是财会 Agent'))
print('need_more_info:', r.need_more_info)
print('user_model:', r.user_model)
"
```

Expected: 输出含 user_model（target=保研）或带 1 个 follow-up question。

- [ ] **Step 3: Commit**

```bash
git add services/coach.py
git commit -m "feat(coach): add onboard with fallback"
```

---

### Task A7: services/coach.py — plan

**Files:**
- Modify: `services/coach.py`

- [ ] **Step 1: 添加 plan 函数 + fallback**

在 `services/coach.py` 末尾追加：

```python
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
```

- [ ] **Step 2: Smoke**

```bash
pixi run python -c "
import asyncio
from services.coach import plan
from services.schemas import UserModel, Target
um = UserModel(id='u1', goal='保研', target=Target.BAOYAN)
r = asyncio.run(plan(um, '我做了一个面向中小企业的财会 Agent...'))
print('packet target:', r.interview_packet.target)
print('focus_slots:', r.interview_packet.focus_slots)
"
```

Expected: target=保研，focus_slots 含至少 1 个 S1/S6 偏向的槽位。

- [ ] **Step 3: Commit**

```bash
git add services/coach.py
git commit -m "feat(coach): add plan with target-aware focus_slots fallback"
```

---

### Task A8: services/coach.py — review

**Files:**
- Modify: `services/coach.py`

- [ ] **Step 1: 添加 review 函数**

在 `services/coach.py` 末尾追加：

```python
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
    # review 是 demo 关键路径，重试更多次：fallback=None → 抛错让上游重试
    # 但为防 demo 崩，给一个最小 fallback
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
```

- [ ] **Step 2: Smoke（可在 e2e 阶段统一验，本步骤可只做 import）**

```bash
pixi run python -c "from services.coach import review; print('imported ok')"
```

Expected: `imported ok`.

- [ ] **Step 3: Commit**

```bash
git add services/coach.py
git commit -m "feat(coach): add review with minimal fallback for evaluation report"
```

---

### Task A9: services/interviewer.py — 状态机辅助函数 + REQUIRED_SLOTS

**Files:**
- Create: `services/interviewer.py`
- Test: `tests/test_state_machine.py`

- [ ] **Step 1: 写 tests/test_state_machine.py**

```python
from services.schemas import (
    InterviewStage, InterviewSession, InterviewTurn, InterviewerOS,
    InterviewPacket, UserModel, Target, RiskLevel, QuestionSource,
)
from services.interviewer import (
    REQUIRED_SLOTS, should_advance, is_vague, update_vague_counter,
    SLOT_COVERAGE_THRESHOLD, VAGUE_SCORE_THRESHOLD, VAGUE_DEGRADE_COUNT,
)


def _mk_session(state=InterviewStage.S1_MOTIVATION):
    return InterviewSession(
        session_id="s",
        user_model=UserModel(id="u", goal="g", target=Target.BAOYAN),
        packet=InterviewPacket(
            target=Target.BAOYAN, interviewer_style="x",
            project_summary="p", focus_slots=[],
        ),
        state=state,
    )


def _mk_turn(state, covered, score=80, missing=None):
    return InterviewTurn(
        id="t", session_id="s", state=state,
        question="q", answer="a", score=score,
        covered_slots=covered, missing_slots=missing or [],
        feedback="f", next_question="nq", source=QuestionSource.PROJECT,
        interviewer_os=InterviewerOS(
            hidden_concern="x", why_this_question="y",
            missing_slots=[], what_i_want_to_hear=[],
            risk_level=RiskLevel.LOW,
        ),
    )


def test_required_slots_has_all_six_states():
    for state in InterviewStage:
        if state == InterviewStage.DONE:
            continue
        assert state in REQUIRED_SLOTS
        assert len(REQUIRED_SLOTS[state]) >= 4


def test_should_advance_when_coverage_high():
    session = _mk_session()
    session.turns = [
        _mk_turn(InterviewStage.S1_MOTIVATION,
                 covered=REQUIRED_SLOTS[InterviewStage.S1_MOTIVATION][:4])
    ]
    # 4 / 5 = 0.8 → 满足 threshold
    assert should_advance(session, session.turns[-1]) is True


def test_should_not_advance_when_coverage_low():
    session = _mk_session()
    session.turns = [
        _mk_turn(InterviewStage.S1_MOTIVATION, covered=["why_do"])
    ]
    # 1 / 5 = 0.2 → 不够
    assert should_advance(session, session.turns[-1]) is False


def test_is_vague_below_threshold():
    turn = _mk_turn(InterviewStage.S1_MOTIVATION, covered=[], score=30)
    assert is_vague(turn) is True
    turn2 = _mk_turn(InterviewStage.S1_MOTIVATION, covered=[], score=60)
    assert is_vague(turn2) is False


def test_vague_counter_increments_and_resets():
    session = _mk_session()
    update_vague_counter(session, _mk_turn(InterviewStage.S1_MOTIVATION, [], score=20))
    assert session.consecutive_vague_count == 1
    update_vague_counter(session, _mk_turn(InterviewStage.S1_MOTIVATION, [], score=20))
    assert session.consecutive_vague_count == 2
    update_vague_counter(session, _mk_turn(InterviewStage.S1_MOTIVATION, ["x"], score=80))
    assert session.consecutive_vague_count == 0
```

- [ ] **Step 2: Run test → 应失败**

```bash
pixi run pytest tests/test_state_machine.py -v
```

Expected: ImportError.

- [ ] **Step 3: 写 services/interviewer.py 的状态机部分**

```python
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
```

- [ ] **Step 4: Run test → 应通过**

```bash
pixi run pytest tests/test_state_machine.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/interviewer.py tests/test_state_machine.py
git commit -m "feat(interviewer): add state machine helpers + required slots"
```

---

### Task A10: services/interviewer.py — start

**Files:**
- Modify: `services/interviewer.py`

依赖 Plan1B 的 `services/question_bank.py`。如未实现可先 stub `QuestionBank` 类（`query` 始终返回 `None`），实施完成后接入。

- [ ] **Step 1: 给 question_bank stub（如未存在）**

```bash
test -f services/question_bank.py || cat > services/question_bank.py <<'EOF'
"""Stub — 实际实现在 Plan1B Task B2。"""
from services.schemas import QuestionCard, Target, InterviewStage


class QuestionBank:
    def __init__(self, *args, **kwargs): pass
    def query(self, target: Target, state: InterviewStage,
              project_tags: list[str] = [],
              exclude_ids: list[str] = []) -> QuestionCard | None:
        return None
EOF
```

- [ ] **Step 2: 在 services/interviewer.py 末尾追加 start**

```python
import uuid

from services.llm import call_deepseek
from services.prompts import INTERVIEWER_SYSTEM
from services.schemas import (
    InterviewerOS, InterviewPacket, QuestionSource, RiskLevel, UserModel,
)
from services.question_bank import QuestionBank
from services.store import SessionStore


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
```

- [ ] **Step 3: Smoke**

```bash
pixi run python -c "
import asyncio
from services.interviewer import start
from services.store import SessionStore
from services.question_bank import QuestionBank
from services.schemas import InterviewPacket, UserModel, Target
packet = InterviewPacket(target=Target.BAOYAN, interviewer_style='技术老师',
                        project_summary='AI 财会助理', focus_slots=['baseline'])
um = UserModel(id='u', goal='保研', target=Target.BAOYAN)
sid, turn = asyncio.run(start(packet, um, QuestionBank(), SessionStore()))
print('sid:', sid[:8])
print('q:', turn.question[:80])
"
```

Expected: 输出第一问（与项目动机相关）。

- [ ] **Step 4: Commit**

```bash
git add services/interviewer.py services/question_bank.py
git commit -m "feat(interviewer): add start with bank lookup + llm fallback"
```

---

### Task A11: services/interviewer.py — next_turn + select_next_question

**Files:**
- Modify: `services/interviewer.py`

- [ ] **Step 1: 在 services/interviewer.py 末尾追加**

```python
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
    new_turn = InterviewTurn(
        id=uuid.uuid4().hex,
        session_id=session_id,
        state=session.state,
        question=last_turn.question,
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
    advance = should_advance(session, new_turn)

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
```

- [ ] **Step 2: Run state machine tests 仍通过**

```bash
pixi run pytest tests/test_state_machine.py -v
```

Expected: 5 PASS（不应被 next_turn 改动破坏）.

- [ ] **Step 3: e2e smoke（可选，依赖真实 LLM）**

```bash
pixi run python -c "
import asyncio
from services.interviewer import start, next_turn
from services.store import SessionStore
from services.question_bank import QuestionBank
from services.schemas import InterviewPacket, UserModel, Target
packet = InterviewPacket(target=Target.BAOYAN, interviewer_style='技术老师',
                        project_summary='AI 财会助理：解析 Excel 自动算公式', focus_slots=['baseline'])
um = UserModel(id='u', goal='保研', target=Target.BAOYAN)
store = SessionStore()
bank = QuestionBank()

async def go():
    sid, t = await start(packet, um, bank, store)
    print('Q1:', t.question[:80])
    new_t, cont, st = await next_turn(sid, '我们做了几次用户访谈，发现真的很需要', bank, store)
    print('feedback:', new_t.feedback[:80])
    print('missing:', new_t.missing_slots)
    print('next_state:', st.value)

asyncio.run(go())
"
```

Expected: feedback 指出缺什么，missing 非空，next_state 仍 S1（未达 80% 覆盖）。

- [ ] **Step 4: Commit**

```bash
git add services/interviewer.py
git commit -m "feat(interviewer): add next_turn with state machine + bank/llm dispatch"
```

---

### Task A12: 端到端 smoke + 整理

**Files:**
- Create: `scripts/smoke_e2e.py` (可选)

- [ ] **Step 1: （可选）写 e2e smoke 脚本**

```python
# scripts/smoke_e2e.py
"""一次性 e2e smoke：onboard → plan → start → next ×3 → review。"""
import asyncio
from services.coach import onboard, plan, review
from services.interviewer import start, next_turn
from services.store import SessionStore
from services.question_bank import QuestionBank


async def main():
    store = SessionStore()
    bank = QuestionBank()

    # onboard
    o = await onboard("我准备保研人工智能创新中心，项目是 AI 财会助理")
    print("onboard need_more_info:", o.need_more_info)
    if o.need_more_info:
        o = await onboard("target=保研，program=人工智能创新中心，最怕被问 baseline",
                          history=[
                              {"role": "user", "content": "我准备保研..."},
                              {"role": "assistant", "content": str(o.followup_questions)},
                          ])
    user_model = o.user_model
    if user_model is None:
        print("⚠ onboarding fallback path; using minimal user_model")
        from services.schemas import UserModel, Target
        user_model = UserModel(id="u1", goal="保研", target=Target.BAOYAN)

    # plan
    p = await plan(user_model, "AI 财会助理：解析 Excel 自动算公式")
    print("plan focus_slots:", p.interview_packet.focus_slots)

    # interview
    sid, t = await start(p.interview_packet, user_model, bank, store)
    print("Q1:", t.question[:80])
    answers = [
        "我们做了用户访谈，痛点确实存在",
        "用 GPT-4 + 规则引擎，输入是 Excel，输出是公式",
        "我们用样例数据测，结果符合预期",
    ]
    for a in answers:
        nt, cont, st = await next_turn(sid, a, bank, store)
        print(f"  state={st.value} score={nt.score} miss={nt.missing_slots}")
        if not cont:
            break

    # review
    session = store.get(sid)
    rep = await review(user_model, p.interview_packet, session.turns)
    print("Report score:", rep.overall_score)
    print("Resume rewrite preview:", rep.resume_rewrite.rewritten[:100])

asyncio.run(main())
```

- [ ] **Step 2: 跑一遍**

```bash
pixi run python scripts/smoke_e2e.py
```

Expected: 完整跑通；任何 fallback 触发会在 stdout 注明 ⚠。

- [ ] **Step 3: 修任何 bug，重跑直到通过**

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_e2e.py
git commit -m "test(e2e): add backend smoke script for onboard → review chain"
```

---

## Self-review

**Spec coverage**：
- §1 模块边界 ✓ Task A0
- §2 数据契约 ✓ Task A2
- §3 LLM 封装 ✓ Task A5
- §4.1 onboard / 4.2 plan / 4.3 review ✓ Tasks A6/A7/A8
- §5 Interviewer state machine + start + next_turn + S6 双模板 ✓ Tasks A9/A10/A11
- §6 Persistence ✓ Task A4
- §7 错误处理 ✓ A5 (impl), A6/A7/A8 (fallbacks), A11 (state machine fallback)
- §8 测试 ✓ A2/A4/A5/A9 各有测试
- §9 实施顺序 ✓ A0→A2→A3→A4→A5→A6→A7→A8→A9→A10→A11→A12

**Placeholder scan**：无 TBD / TODO；每个步骤有具体代码或具体命令。

**Type consistency**：
- `OnboardResult` / `CoachPlanResult` / `EvaluationReport` / `InterviewTurn` 命名贯穿 schemas → coach → interviewer，一致
- `QuestionBank.query` 签名（target, state, project_tags, exclude_ids）在 A10/A11 与 Plan1B Task B2 对齐
- `SessionStore.create / get / append_turn` 签名贯穿 A4 与 A10/A11 一致

**实施依赖外部**：
- Plan1B Task B2 完成后 `services/question_bank.py` 真实实现替换 A10 stub
- Plan1C 实施时直接 import services.coach / services.interviewer 即可
