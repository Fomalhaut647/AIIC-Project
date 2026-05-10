# Spec A — 后端智能：数据契约 / LLM 封装 / Coach / Interviewer / Persistence

> 起草日期：2026-05-10
> 父文档：[../overview.md](../overview.md)
> 范围：所有 Python 业务逻辑（除 API 路由层 → 见 [Spec C](C-api-and-frontend.md)；除合成题库脚本 → 见 [Spec B](B-question-bank.md)）

---

## 1. 模块边界

```
services/
├── schemas.py        Pydantic 数据契约（全部类型定义）
├── llm.py            DeepSeek 调用封装 + JSON repair + fallback
├── prompts.py        所有 LLM prompt 字面常量
├── coach.py          Coach agent (onboard / plan / review)
├── interviewer.py    Interviewer agent (start / next / state machine / OS)
├── store.py          in-memory + JSON fallback persistence
└── question_bank.py  题库读取与查询（见 Spec B；这里只列依赖）
```

依赖图（→ 表示「依赖」，DAG 无环）：

```
schemas ←─ llm
schemas ←─ store
schemas, llm, prompts ←─ coach
schemas, llm, prompts, store, question_bank ←─ interviewer
```

实施顺序：`schemas → llm → prompts → store → question_bank → coach → interviewer`。

---

## 2. 数据契约（services/schemas.py）

全部使用 Pydantic v2。所有类型在 `schemas.py` 内集中定义，不分文件。

### 2.1 Enum

```python
from enum import Enum

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
    PROJECT = "project"           # LLM 基于项目和上一轮回答现场生成
    BANK = "synthetic_question_bank"  # 从合成题库匹配
    BASIC = "basic_concept"       # 项目相关基础概念
    FALLBACK = "fallback"         # 兜底通用题
```

### 2.2 用户与项目

```python
from pydantic import BaseModel, Field

class ProjectSummary(BaseModel):
    title: str
    one_liner: str  # ≤80 字符
    technical_keywords: list[str] = []
    likely_followup_directions: list[str] = []  # 由 profile/parse 抽取

class UserModel(BaseModel):
    id: str  # uuid4 hex
    goal: str  # 自由文本：用户原始需求陈述
    target: Target
    target_program: str | None = None  # e.g. "人工智能创新中心" / "字节 AI Lab 实习"
    projects: list[ProjectSummary] = []
    strengths: list[str] = []
    recurring_weaknesses: list[str] = []
    resume_issues: list[str] = []
    preferred_style: PreferredStyle = PreferredStyle.DIRECT
    current_stage: TrainingMode = TrainingMode.NORMAL
```

### 2.3 训练计划与面试包

```python
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
    interviewer_style: str  # 自由文本：e.g. "技术老师 + 创业评委混合"
    intensity: RiskLevel = RiskLevel.MEDIUM
    project_summary: str
    focus_slots: list[str]  # 重点 slot 名（与 §5.1 REQUIRED_SLOTS 对应）
    constraints: list[str] = []
    question_policy: str = "项目优先 → 题库匹配 → 基础概念 → 八股兜底"
```

### 2.4 面试 turn

```python
class InterviewerOS(BaseModel):
    """作弊模式：面试官内心判断（面向用户的判断摘要，非完整 CoT）"""
    hidden_concern: str
    why_this_question: str
    missing_slots: list[str]
    what_i_want_to_hear: list[str]
    risk_level: RiskLevel

class InterviewTurn(BaseModel):
    id: str  # uuid4 hex
    session_id: str
    state: InterviewStage
    question: str
    answer: str
    score: int = Field(ge=0, le=100)  # LLM 评估的回答完整度
    covered_slots: list[str]
    missing_slots: list[str]
    feedback: str  # 给用户看的简短点评
    next_question: str
    source: QuestionSource
    interviewer_os: InterviewerOS
```

### 2.5 复盘报告

```python
class Evidence(BaseModel):
    quote: str  # 用户原话片段（必须真实存在于某 turn.answer）
    problem: str
    suggestion: str

class ResumeRewrite(BaseModel):
    original: str
    rewritten: str
    missing_evidence: list[str]  # 改写后仍缺的证据点

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
```

### 2.6 Coach API 输出

```python
class OnboardResult(BaseModel):
    """coach.onboard 返回"""
    need_more_info: bool
    followup_questions: list[str] = []  # need_more_info=True 时非空
    user_model: UserModel | None = None  # need_more_info=False 时非空
    recommended_packet: InterviewPacket | None = None  # 同上

class CoachPlanResult(BaseModel):
    """coach.plan 返回"""
    training_plan: TrainingPlan
    interview_packet: InterviewPacket
```

### 2.7 Session 状态（store 内部用）

```python
class InterviewSession(BaseModel):
    session_id: str
    user_model: UserModel
    packet: InterviewPacket
    state: InterviewStage = InterviewStage.S1_MOTIVATION
    turns: list[InterviewTurn] = []
    consecutive_vague_count: int = 0
    used_question_ids: list[str] = []  # 已从题库取过的 QuestionCard.id
```

`QuestionCard` 定义见 [Spec B §6](B-question-bank.md)（避免循环依赖：`question_bank.py` import schemas 而非反向）。

---

## 3. LLM 封装（services/llm.py）

### 3.1 公开 API

```python
from typing import TypeVar
T = TypeVar("T", bound=BaseModel)

async def call_deepseek(
    messages: list[dict],
    *,
    response_schema: type[T] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    fallback: T | str | None = None,
    stream: bool = False,
) -> T | str | AsyncIterator[str]:
    """
    - response_schema 给定 → 返回 schema 实例（JSON 解析 + Pydantic 校验）
    - response_schema=None + stream=False → 返回纯文本
    - stream=True → 返回 AsyncIterator[str]，逐 chunk yield content
                    （仅 response_schema=None 时支持 stream，结构化输出强制 non-stream）
    - JSON 校验失败 → repair retry 一次（带原始输出 + 错误信息进 prompt）
    - 仍失败 → 返回 fallback；fallback=None → 抛 LLMSchemaError
    """
```

### 3.2 配置加载（从 .env）

```python
import os
from dotenv import load_dotenv
load_dotenv()

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
```

### 3.3 OpenAI 兼容 client

DeepSeek 提供 OpenAI 兼容 endpoint，复用 `httpx.AsyncClient`（v1 已熟悉）：

```python
async def _post_chat(messages, temperature, max_tokens, stream):
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if not stream:
        body["response_format"] = {"type": "json_object"}  # 仅当 response_schema is not None
    # httpx call to {DEEPSEEK_BASE_URL}/v1/chat/completions
```

### 3.4 JSON 输出 prompt 注入

`response_schema` 给定时，自动在最后一条 message 后追加（不动 system，避免与 Coach/Interviewer 自身 system prompt 冲突）：

```python
JSON_OUTPUT_INSTRUCTION = """
**严格输出要求**：
- 只输出合法 JSON，不要带 Markdown 代码块包裹
- 字段必须严格符合下方 schema
- 不要输出任何解释文字、前缀、后缀
- 字符串值中的引号、换行需正确转义

JSON Schema:
{schema_json}
"""
```

`{schema_json}` = `response_schema.model_json_schema()` 序列化结果。

### 3.5 Repair retry prompt

```python
JSON_REPAIR_INSTRUCTION = """
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

repair retry 仅一次。再失败 → fallback。

### 3.6 Logging

每次调用写一行结构化 log 到 `logs/llm.log`：

```
2026-05-10T14:23:00Z | role=coach.onboard | prompt_chars=1234 | resp_chars=567 | repair=False | fallback=False | duration_ms=2103
```

便于 demo 后回放调用链 + 调试 fallback 触发。

---

## 4. Coach agent（services/coach.py）

### 4.1 onboard

签名：

```python
async def onboard(user_message: str, history: list[dict] = []) -> OnboardResult:
    """
    history 是之前 onboard 轮次的 [{role: user|assistant, content}] 列表。
    返回 need_more_info=True → 前端继续问；False → 进入材料输入页。
    """
```

prompt skeleton（system；完整字面在 `prompts.py:COACH_ONBOARD_SYSTEM`）：

```
你是 ProjectProbe 的训练组长 Coach。你的任务是了解用户的目标和需求，
最终生成 UserModel 和推荐的 InterviewPacket。

第一轮必问场景：用户准备的是「保研复试」「AI 岗位面试」还是「混合」。
如果用户的初始消息已明确表达，直接抽取，不要重复问。

完成下列任务后输出 OnboardResult：
1. 抽取 target、target_program、preferred_style
2. 让用户简述项目（不需要详细，只要标题 + 一句话）
3. 让用户说出当前最害怕被追问的方向（用于 focus_slots）

如果信息不全，need_more_info=True + followup_questions（≤2 题，简短）。
如果信息够，need_more_info=False + 完整 user_model + recommended_packet。

不要替用户回答面试问题。不要给宏观训练计划（那是 plan 阶段的事）。
```

### 4.2 plan

签名：

```python
async def plan(user_model: UserModel, project_summary: str) -> CoachPlanResult:
    """
    根据 user_model + 项目摘要生成训练路线 + 面试包。
    project_summary 来自 /api/profile/parse（Spec C §2.2）。
    """
```

prompt skeleton：

```
你是 ProjectProbe 的训练组长 Coach。基于以下信息生成训练计划：

UserModel:
{user_model}

ProjectSummary:
{project_summary}

输出：
1. TrainingPlan：选择 recommended_next_step（普通项目面 / 压力面 / 简历修改 / 薄弱项重练），
   给出 reason，列 ≥2 个 TrainingStep。
2. InterviewPacket：focus_slots 必须 target-aware：
   - 保研 → 偏 S1（项目动机）+ S6（研究匹配）+ S4（实验验证）
   - 求职 → 偏 S3（技术深挖）+ S4（实验验证）+ S5（失败反思）
   - 混合 → S3 + S4 + S6 各占一份
   focus_slots ≤5 个（贪多 = 没重点）。
```

### 4.3 review

签名：

```python
async def review(
    user_model: UserModel,
    packet: InterviewPacket,
    turns: list[InterviewTurn],
) -> EvaluationReport:
    """面试结束后生成全局复盘。"""
```

prompt skeleton：

```
你是 ProjectProbe 的训练组长 Coach。面试已结束。基于完整 turns 生成 EvaluationReport。

UserModel: {user_model}
InterviewPacket: {packet}
Turns: {turns}

要求：
1. evidence[].quote 必须是 turns 中真实出现的用户原话片段，不能改写
2. dangerous_questions 必须是 ≥2 个未来面试官最可能继续追问的题
3. resume_rewrite.rewritten 要把面试中暴露的真实细节纳入，不能凭空捏造
4. resume_rewrite.missing_evidence 列出改写后仍缺的证据点（让用户知道接下来要补什么）
5. next_training_plan 必须给 ≥2 个 TrainingStep
6. humor_card 规则（强约束）：
   - 必须引用本轮真实暴露的具体 missing_slot
   - 把它解释为「高价值 bug」/ 调试梗 / 数学梗 / 论文梗
   - 不允许「加油，你一定行」类空泛鸡汤
   - 结尾给一个具体的下一步动作
7. preferred_style 影响语气（直接 / 温和 / 幽默），但不影响 humor_card 的幽默基调
```

### 4.4 fallback 模板

```python
ONBOARD_FALLBACK = OnboardResult(
    need_more_info=True,
    followup_questions=["我没能理解你的需求。可以告诉我你这次主要是为了准备保研还是 AI 岗位面试吗？"],
)

PLAN_FALLBACK = CoachPlanResult(
    training_plan=TrainingPlan(
        recommended_next_step=TrainingMode.NORMAL,
        reason="LLM 输出异常，回退到默认普通项目面。",
        steps=[
            TrainingStep(name="项目陈述", goal="把项目讲完整", why_now="主线优先"),
            TrainingStep(name="项目深挖", goal="覆盖 baseline / 实验 / 失败反思", why_now="为复试 / 面试做准备"),
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

# REVIEW_FALLBACK：尽量不返回 fallback（review 是 demo 关键路径），
# 重试更多次；万不得已返回带 "summary='系统繁忙，请稍后重试'" 的最小报告
```

---

## 5. Interviewer agent（services/interviewer.py）

### 5.1 状态机定义

```python
REQUIRED_SLOTS: dict[InterviewStage, list[str]] = {
    InterviewStage.S1_MOTIVATION: [
        "why_do",              # 为什么做
        "target_user",         # 目标用户
        "pain_real",           # 痛点真实性
        "timing",              # 为什么现在做
        "direction_relevance", # 与 AI 方向关系
    ],
    InterviewStage.S2_OVERVIEW: [
        "goal", "io", "architecture", "user_flow",
        "personal_contribution",  # 重点
    ],
    InterviewStage.S3_TECHNICAL: [
        "tech_solution", "method_choice_reason", "key_modules",
        "alternatives", "engineering_details",
    ],
    InterviewStage.S4_VALIDATION: [
        "baseline",  # 重点
        "metric", "data_source", "evaluation_method",
        "control_experiment", "error_analysis",
    ],
    InterviewStage.S5_REFLECTION: [
        "failure_case", "edge_condition", "current_limit",
        "risk_control", "improvement",
    ],
    InterviewStage.S6_MATCHING: [
        # 按 target 双模板：
        # 保研 → ["research_direction_match", "future_research", "personal_growth", "fit_reason"]
        # 求职 → ["job_role_match", "system_design_growth", "personal_growth", "fit_reason"]
        "match_to_target",  # 抽象槽位，运行时按 target 展开
        "future_direction",
        "personal_growth",
        "fit_reason",
    ],
}
```

### 5.2 推进规则

```python
SLOT_COVERAGE_THRESHOLD = 0.8  # 覆盖 ≥80% 的 required slots → 进入下一 state
VAGUE_SCORE_THRESHOLD = 40     # LLM score < 40 → 视为空泛
VAGUE_DEGRADE_COUNT = 3        # 连续 3 次空泛 → 降级追问

def should_advance(session: InterviewSession, latest_turn: InterviewTurn) -> bool:
    required = set(REQUIRED_SLOTS[session.state])
    # 累积本 state 内所有 turn 的 covered_slots
    covered_in_state = set()
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
```

### 5.3 next_question 选择

```python
async def select_next_question(
    session: InterviewSession,
    latest_turn: InterviewTurn,
    bank: QuestionBank,
) -> tuple[str, QuestionSource]:
    """
    优先级（从高到低）：
    1. latest_turn.missing_slots 非空且 NOT should_advance
       → LLM 生成针对 missing_slot 的追问 (PROJECT)
    2. should_advance(session, latest_turn) → 推进 state，从题库选下一 state 的开场题
       bank.query(target=packet.target, state=new_state, project_tags=...,
                  exclude_ids=session.used_question_ids) → BANK
    3. 题库无匹配 → LLM 基于 new_state required_slots 现场生成 (PROJECT)
    4. 连续空泛 ≥3 → 降级到基础概念问题 (BASIC)
    5. 兜底：通用八股 (FALLBACK)
    """
```

### 5.4 interviewer.start

签名：

```python
async def start(packet: InterviewPacket, user_model: UserModel) -> tuple[str, InterviewTurn]:
    """
    创建 InterviewSession，生成第一问（state=S1_MOTIVATION）。
    返回 (session_id, first_turn)。first_turn 的 answer="" / score=0 / covered_slots=[]
    （只用 question + interviewer_os 字段）。
    """
```

第一问策略：从题库 query S1 开场题；无 → LLM 现场生成（基于 packet.project_summary 抓项目动机切入）。

### 5.5 interviewer.next

签名：

```python
async def next_turn(
    session_id: str,
    answer: str,
    bank: QuestionBank,
    store: SessionStore,
) -> tuple[InterviewTurn, bool, InterviewStage]:
    """
    返回 (new_turn, should_continue, next_state)。
    should_continue=False 当 next_state == DONE。
    """
```

prompt skeleton（Interviewer system；完整字面在 `prompts.py:INTERVIEWER_SYSTEM`）：

```
你是 ProjectProbe 模拟面试官。你模拟的是第一次见到候选人的 {target_role}。

你只能看到：
- InterviewPacket: {packet}
- 当前 state: {state}
- required_slots（本 state）: {required}
- 当前对话历史: {turns}

每次用户回答后，输出 InterviewTurn 必须的字段（除 id/session_id）：
- score (0-100)：回答完整度（覆盖 required_slots 的程度）
- covered_slots: 用户回答覆盖了哪些 slot 名（从 required_slots 选）
- missing_slots: 哪些 required_slots 没覆盖
- feedback (≤80 字符)：给用户的简短点评，点明缺什么
- next_question: 下一问（优先针对 missing_slots，否则推进 state 后的开场题）
- source: 见 QuestionSource enum
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
```

### 5.6 S6 双模板

S6 进入时，按 `packet.target` 选用对应 prompt 片段（hardcode 在 `prompts.py:S6_BAOYAN_TEMPLATE` / `S6_QIUZHI_TEMPLATE` / `S6_HUNHE_TEMPLATE`）。混合 = 前 2 题走保研模板，后 2 题走求职模板。

---

## 6. Persistence（services/store.py）

```python
from pathlib import Path
import json, uuid
from contextlib import suppress

class SessionStore:
    def __init__(self, dump_dir: Path = Path("data/sessions")):
        self._sessions: dict[str, InterviewSession] = {}
        self._dump_dir = dump_dir
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
        # fire-and-forget dump
        self._dump_async(session)

    def _dump_async(self, session: InterviewSession) -> None:
        # 同步写文件足够：JSON dump 单 session ≤200KB，<5ms
        path = self._dump_dir / f"{session.session_id}.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
```

不实现 `load_from_disk`：服务重启 = session 丢，可接受。dump 仅为人工复盘。

---

## 7. 错误处理与降级

| 错误 | 处理 |
|---|---|
| LLM 网络超时（httpx.TimeoutException） | retry 一次（5s 后）；仍失败 → fallback 模板 |
| LLM 返回非合法 JSON | repair retry 一次；仍失败 → fallback |
| LLM 返回 JSON 但 schema 校验失败 | repair retry 一次（带 ValidationError 进 prompt）；仍失败 → fallback |
| missing_slots 全空 + 用户输入也空 | Interviewer 切到「项目背景澄清」分支（基础概念问 + 要求 1 句话描述项目） |
| InterviewSession 找不到 | API 层返回 404 + body `{"error": "session_expired", "message": "请重新开始训练"}` |
| QuestionBank 文件缺失 / 损坏 | 启动时检测；缺失 → fallback 到 12 seed；损坏 → 抛错让用户重新合成 |

异常类型：

```python
class LLMSchemaError(Exception): pass
class SessionNotFound(KeyError): pass
class QuestionBankError(Exception): pass
```

---

## 8. 测试策略

P0 不写完整端到端测试套件（时间紧）。最小测试集：

```
tests/
├── test_schemas.py          Pydantic 校验关键字段（boundary / enum / required）
├── test_state_machine.py    should_advance / is_vague / vague counter 纯逻辑
├── test_llm_repair.py       mock httpx，验证 repair retry 和 fallback 触发
└── test_store.py            create / get / append / dump 持久化
```

**不写**：Coach / Interviewer 端到端测试（依赖真实 LLM，不稳定，由 demo 验证替代）。

`pixi run test` 沿用 v1 的 pytest 配置。

---

## 9. 实施顺序

```
Step 1: schemas.py        无依赖，先写
Step 2: prompts.py        无依赖，与 Step 1 并行
Step 3: store.py          依赖 schemas
Step 4: llm.py            依赖 schemas
Step 5: question_bank.py  依赖 schemas（Spec B 实现）
Step 6: coach.py          依赖 schemas + llm + prompts
Step 7: interviewer.py    依赖 schemas + llm + prompts + store + question_bank
```

Step 1-2-4 可由一个 implementer 一气呵成。Step 5（合成题库脚本 + query API）独立 implementer 并行。Step 6-7 互相独立，可并行。
