# Spec D — Plan2 长期训练闭环：Session 持久化 / 重练 / 简历多轮 / Markdown 导出 / 个人主页

> 起草日期：2026-05-10
> 父文档：[../overview.md](../overview.md)
> 上游依赖：Spec A（services/）/ Spec C（API + 前端 SPA）已交付的 v2 现状
> 范围：Plan2 = F1 + F2 + F4 + F5 + F7 五条 feature；不含 F3（跨 session 演化趋势图）/ F6（PDF 解析）/ F8（多项目对比）

---

## 1. 范围

### 1.1 In-scope

| 编号 | feature | 一句话 |
|---|---|---|
| **F1** | Session 持久化 + 用户回访 | 引入 anonymous user_id（localStorage uuid），后端 user-aware 存储 |
| **F2** | 一键重练薄弱项 | 复盘报告或个人主页点弱点 → 派生 replay session，只追问指定 slot；结束输出 mini-report |
| **F4** | 简历改写多轮迭代 | 用户改完 resume 粘回 → Coach 评估 missing_evidence 是否被覆盖；不限轮次，自然收敛 |
| **F5** | 报告导出 Markdown | 后端生成 8-section Markdown 文件；UI 入口在报告页 + 个人主页每行 |
| **F7** | 个人主页 dashboard | 新视图 `view-profile`，展示 session 时间线 / 弱点累计 / 项目库 |

### 1.2 Out-of-scope（YAGNI）

- F3 跨 session 弱点演化趋势图（粗略 hero stats 已够）
- F6 PDF / Word / 图片项目材料解析
- F8 多项目主推对比模式
- 跨设备 user_id 导出 / 导入
- 完整登录系统 / OAuth / SSO / 账号迁移
- 多用户管理后台
- WebSocket / 实时多人协作
- 精确训练时长计时（用 session 数估算即可）

---

## 2. 设计哲学

> v2 已经靠**作弊模式**立住了"元认知"维度对 ChatGPT 的差异化。Plan2 立"**长期训练**"维度。

ChatGPT 的根本限制是**单 session 无记忆 + 无主动训练计划**：
- 用户每次重新粘项目材料，Coach 不知道你昨天答得多空
- 弱点暴露后没有"针对该弱点的下一轮训练"机制
- 简历改写出"missing_evidence"，但用户改完后没有验证回路

Plan2 的每条 feature 都直接对应某个 ChatGPT 做不到的训练动作：

| feature | ChatGPT 做不到 |
|---|---|
| F1 持久化 | 跨 session 记得你 |
| F2 一键重练 | 把上轮弱点直接转成下一轮训练焦点 |
| F4 简历多轮 | 评估改写是否真的覆盖 missing_evidence |
| F5 Markdown 导出 | 让用户拿走完整复盘（含面试官 OS）离线对照 |
| F7 个人主页 | 让用户看见"我在哪里弱"+ 弱点演化 |

每条都能在答辩 / Demo 视频里讲"这是 ChatGPT 不能做但 ProjectProbe 能做的事"，对应评分核心句"相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试"。

---

## 3. 用户身份机制（无登录方案）

### 3.1 前端

```javascript
// web/app.js 启动时
const userId = localStorage.getItem('userId') || (() => {
  const id = crypto.randomUUID();
  localStorage.setItem('userId', id);
  return id;
})();
```

每次 API 调用 body 加 `user_id` 字段（GET 走 path param `/api/users/{user_id}/...`）。

### 3.2 后端

- 所有现有 POST endpoint body 加可选字段 `user_id: str = "anonymous"`
- 缺失或为空字符串 → fallback `"anonymous"`
- `"anonymous"` 是合法 user_id，所有 anonymous 流量共享同一 profile（不区分；用户清缓存即等价于回到 anonymous 群）

### 3.3 不做

- cookie / SSO / 第三方 OAuth
- user_id 跨设备导出 / 导入 / 二维码同步
- 用户名 / 邮箱 / 任何 PII 收集
- 服务端识别"同一真人"（清缓存 = 重生为新用户，这是设计意图）

---

## 4. 持久化布局

### 4.1 文件结构

沿用 v2 §10「不上 SQLite」约束，扩展现有 `services/store.py`（in-memory dict + 异步 JSON dump）：

```
data/
├── sessions/<session_id>.json       # 沿用 v2，session 内加 user_id 字段
├── users/<user_id>.json              # 新增：UserProfile 聚合视图
└── question_bank.{seed,synthetic}.json   # v2 不动
```

**双索引**：sessions 平铺便于 grep / 单 session 查询；user profile 单文件聚合便于 dashboard 一次拉取。

### 4.2 SessionStore 新方法

```python
class SessionStore:
    # v2 已有
    def save(self, session_id: str, payload: dict) -> None: ...
    def load(self, session_id: str) -> dict | None: ...

    # Plan2 新增
    def list_user_sessions(self, user_id: str) -> list[SessionMeta]: ...
    def update_user_profile(self, user_id: str, session_meta: SessionMeta) -> None: ...
    def load_user_profile(self, user_id: str) -> UserProfile: ...  # 不存在 → 空 UserProfile
```

`update_user_profile` 在 `/api/coach/review` 完成后由 server 层调用，做：
- append 该 session 的 `SessionMeta` 到 `user_profile.sessions`
- 累计 `weakness_tags` 到 `recurring_weaknesses[slot] += 1`
- 去重 append `project_summary_short` 到 `projects[]`
- 重算 `total_sessions` / `average_score`

### 4.3 兼容性

- 现有 v2 `data/sessions/*.json` 缺 `user_id` 字段 → Pydantic schema 加 `user_id: str = "anonymous"` 默认值兜底
- 启动时不做迁移脚本；老 session 自然以 anonymous 身份进入新 dashboard

---

## 5. 数据契约新增（services/schemas.py）

### 5.1 SessionMeta（新）

```python
class SessionMeta(BaseModel):
    session_id: str
    created_at: datetime
    target: Target  # 复述 v2: Literal["保研","求职","混合"]
    project_summary_short: str        # project_summary 前 80 字
    overall_score: int | None = None  # review 完成后才有
    weakness_tags: list[str] = []      # 从 EvaluationReport.weaknesses 提取的 slot 名
    parent_session_id: str | None = None  # 重练 session 时指向原 session
    is_replay: bool = False
```

### 5.2 UserProfile（新）

```python
class UserProfile(BaseModel):
    user_id: str
    created_at: datetime
    sessions: list[SessionMeta] = []
    total_sessions: int = 0
    average_score: float | None = None
    recurring_weaknesses: dict[str, int] = {}  # canonicalized slot name → count
    projects: list[str] = []                    # 去重的 project_summary_short

    def add_session_meta(self, meta: SessionMeta) -> None:
        """聚合一条新 session：append + 重算 hero stats + 累计弱点"""
```

### 5.3 InterviewPacket 加字段

```python
class InterviewPacket(BaseModel):
    # v2 已有
    target: Target
    interviewer_style: str
    intensity: int
    project_summary: str
    focus_slots: list[str]
    constraints: dict
    question_policy: dict

    # Plan2 新增
    replay_mode: bool = False
    replay_focus_slots: list[str] = []     # 仅 replay_mode=True 时使用
    parent_session_id: str | None = None
```

### 5.4 ResumeRevision（新） + EvaluationReport.resume_rewrite 加字段

```python
class ResumeRevision(BaseModel):
    iteration_index: int  # 从 1 开始
    timestamp: datetime
    user_text: str         # 用户提交的修改稿
    coach_feedback: str    # Coach 评价（≤200 字）
    newly_covered: list[str]
    still_missing: list[str]
    is_good_enough: bool

class ResumeRewrite(BaseModel):
    # v2 已有
    original: str
    rewritten: str
    missing_evidence: list[str]

    # Plan2 新增
    revision_history: list[ResumeRevision] = []
```

### 5.5 ReplayMiniReport（新）

```python
class ReplayMiniReport(BaseModel):
    parent_session_id: str
    replay_session_id: str
    focus_slots: list[str]
    coverage_before: float   # 0.0 - 1.0
    coverage_after: float
    delta_pp: float           # (after - before) * 100，可为负
    sample_good_answer: str   # 重练里答得最好的一句作 evidence（≤200 字）
    next_step: str             # "下次重点继续盯 baseline 的 evaluation 部分"
```

---

## 6. API 接口（新增 + 修改）

### 6.1 新增

| Endpoint | 方法 | 输入 → 输出 |
|---|---|---|
| `/api/users/{user_id}/profile` | GET | path user_id → `UserProfile` |
| `/api/interviewer/replay` | POST | `{parent_session_id, focus_slots, user_id?}` → `{session_id, state, question, packet}` |
| `/api/interviewer/replay/finish` | POST | `{session_id, user_id?}` → `ReplayMiniReport`（仅当 session 是 replay session；否则 400） |
| `/api/coach/resume_iterate` | POST | `{session_id, user_revised_resume, user_id?}` → `ResumeRevision` |
| `/api/sessions/{session_id}/export.md` | GET | path session_id → `text/markdown` 文件流 + `Content-Disposition: attachment` |

### 6.2 修改

- `POST /api/coach/onboard` / `profile/parse` / `coach/plan` / `interviewer/start` / `interviewer/next` / `coach/review` body 加可选 `user_id: str = "anonymous"`
- `POST /api/coach/review` 完成后调用 `SessionStore.update_user_profile(user_id, session_meta)`，将本 session 聚合入 user profile
- `GET /api/healthz` 不变

### 6.3 不复用 `/api/interviewer/start` 的理由

重练 session 不需要走 onboard / plan 链；packet 直接从 `parent_session_id` 派生（拷贝 + 加 `replay_mode=True` + 加 `replay_focus_slots`）。把这个分支塞进 `/api/interviewer/start` 会让 schema 出现两套互斥字段（`onboarding_path` vs `replay_path`），不如开新 endpoint 干净。

---

## 7. F2 重练模式

### 7.1 用户路径

1. 用户在 **复盘报告页** 看到弱点 tags / 在 **个人主页** 看到训练时间线
2. 点击「重练 baseline」按钮
3. 前端 POST `/api/interviewer/replay` `{parent_session_id, focus_slots: ["baseline"]}`
4. 后端构造 `replay_packet` 并启动 Interviewer
5. Interviewer 只追问 `replay_focus_slots`，状态机停留在原 state
6. 用户答 N 轮 → 后端检测 `covered_slots ⊇ replay_focus_slots` → `should_continue=False`
7. 前端 POST `/api/interviewer/replay/finish` 取 mini-report
8. UI 弹 `ReplayMiniReport` 卡片：「baseline 这一槽位覆盖度从 33% 提升到 80%（+47pp）」+ next_step

### 7.2 Replay packet 构造

```python
def build_replay_packet(parent: InterviewPacket, focus_slots: list[str]) -> InterviewPacket:
    return parent.model_copy(update={
        "replay_mode": True,
        "replay_focus_slots": focus_slots,
        "parent_session_id": parent.session_id,
        # 注意：focus_slots 字段保持不变（v2 字段，给 Interviewer 看）
    })
```

### 7.3 Interviewer prompt 改动

`services/prompts.py` 加 `INTERVIEWER_REPLAY_PROMPT_INJECT`，在系统 prompt 末尾追加（仅 `replay_mode=True` 时）：

```
本轮为「重练模式」。规则：
- 只围绕以下 slot 追问，不要扩展话题：{replay_focus_slots}
- 不要前进状态机，停留在 {state}
- 用户已经做过整轮面试，可以直接深入；不需要 warm-up
- 不需要使用任何特殊结束 token；后端会基于 covered_slots 判断是否结束
```

**实现 note**（`interviewer.py` 内部）：
- replay_mode=True 时，状态机推进函数 `should_advance_state` 直接返回 False（state 不前进）
- 终止由后端基于 `covered_slots ⊇ replay_focus_slots` 判定（与 v2 should_continue 模式一致），不引入新 token 协议
- 前端见到 `should_continue=False` 自动调用 `/replay/finish` 取 mini-report

### 7.4 覆盖度闭式计算

由 `coach.py` 新函数 `compute_replay_coverage` 完成：

```python
def compute_replay_coverage(turns: list[InterviewTurn], focus_slots: list[str]) -> float:
    """
    闭式：focus_slots 中被任一 turn 覆盖过的占比。
    用 lowercase + strip 做 slot canonicalization。
    """
    canon = lambda s: s.strip().lower()
    covered = set()
    for turn in turns:
        for slot in turn.covered_slots:
            covered.add(canon(slot))
    focus_canon = {canon(s) for s in focus_slots}
    if not focus_canon:
        return 0.0
    return len(focus_canon & covered) / len(focus_canon)
```

`coverage_before` 用 parent session 的 turns + focus_slots 算；`coverage_after` 用 replay session 的 turns + focus_slots 算。

### 7.5 sample_good_answer 与 next_step

由 `coach.py` 新函数 `summarize_replay(parent_meta, replay_turns, focus_slots) → ReplayMiniReport` 调用 LLM 一次：
- input: 重练所有 turns + focus_slots
- output schema: `{sample_good_answer: str, next_step: str}`
- failure fallback: sample_good_answer = "（无法摘录，请回看原文）" + next_step = "继续围绕 {focus_slots} 多举具体例子"

### 7.6 退出条件细则

- **正常完成**：covered ⊇ focus → `should_continue=False`
- **用户主动放弃**：前端「结束重练」按钮 → 直接调 `/replay/finish`，但 mini-report 的 `coverage_after` 反映实际覆盖（可能 < 100%）
- **超过 8 轮仍未覆盖**：后端硬截断 → `should_continue=False`，mini-report 中 `next_step` 提示「这个 slot 比较难，建议看一下相关知识点再来」

---

## 8. F4 简历多轮迭代

### 8.1 UX

报告页 `resume_rewrite` 块下方加：
- 显示当前 `missing_evidence`（绿色已覆盖 / 灰色待补）
- textarea「我改完了，粘贴新版本」
- 按钮「让 Coach 看看」
- 历次 `revision_history` 折叠展示

### 8.2 后端流程

```python
POST /api/coach/resume_iterate
body: {
  session_id: str,
  user_revised_resume: str,
  user_id: str | None
}
returns: ResumeRevision
```

`coach.py` 新函数 `iterate_resume(original, prior_missing, user_revised) → ResumeRevision`：
- LLM input: 原始 resume + 上一版 missing_evidence + 用户新提交版本
- LLM output schema:
  ```json
  {
    "newly_covered": ["baseline 已说明"],
    "still_missing": ["错误分析的具体 case"],
    "coach_feedback": "...",
    "is_good_enough": false
  }
  ```
- `iteration_index` 由 server 层根据 `len(revision_history)+1` 决定
- `is_good_enough = (still_missing == [])`

### 8.3 不限轮次 + 自然收敛

- 用户可无限次提交；coach 自然递减 `still_missing`
- `is_good_enough=True` 时前端显示绿色 banner「这版差不多可以了；要继续打磨可以再来」
- 不强制截断（用户偏要纠结某条 missing 也允许）

### 8.4 token 控制

- 每次只传 `original` + `prior_missing` + `user_revised`，不累积全部 `revision_history`
- 历史 revision 仅前端展示用，不喂回 LLM
- 单次 LLM 调用 max_tokens 1500 足够

---

## 9. F5 Markdown 导出

### 9.1 接口

```
GET /api/sessions/{session_id}/export.md

200 OK
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="projectprobe-{session_id_short}-{date}-score{N}.md"

(markdown body)

409 Conflict （session 未完成 review；判定方式 = session JSON 中无 EvaluationReport 字段或字段为空）
404 Not Found （session_id 不存在）
```

**session 完成判定**：v2 没有显式 `status` 字段，用「`session.evaluation_report` 是否存在且非空」做隐式判定。这避免 schema 加 status 字段引入更多兼容工作。

### 9.2 后端实现

新模块 `services/export.py`：

```python
def render_markdown(session: dict) -> str:
    """8 段固定模板渲染。session 含完整 InterviewTurn[] + EvaluationReport"""
```

### 9.3 模板（8 段）

```markdown
# ProjectProbe 复盘报告

> 生成时间：{now}
> Session ID：{session_id}

## 1. Session 元数据

- 训练目标：{target}
- 项目：{project_summary_short}
- 训练时间：{created_at} → {finished_at}
- 总分：{overall_score} / 100

## 2. 总体评估

{summary}

**优势**
{strengths_bullet_list}

**弱点**
{weaknesses_bullet_list}

## 3. 关键证据

{evidence_bullet_list}

## 4. 最危险追问

{dangerous_questions_bullet_list}

## 5. 简历改写

### 原始版本
{resume_rewrite.original}

### Coach 改写版本
{resume_rewrite.rewritten}

### 还差的证据
{missing_evidence_bullet_list}

### 历次迭代
（如果 revision_history 非空，每个 revision 一段：iteration_index / timestamp / user_text / coach_feedback / newly_covered / still_missing）

## 6. 下一轮训练计划

{next_training_plan}

## 7. 幽默卡片

**{humor_card.title}**

{humor_card.content}

## 8. 完整对话日志

<details><summary>展开全部 N 轮（含面试官 OS）</summary>

### 第 1 轮 · S{state}
**问题**：{question}

**回答**：{answer}

**反馈**：{feedback}

**面试官 OS（作弊模式）**：
- hidden_concern: {interviewer_os.hidden_concern}
- why_this_question: {interviewer_os.why_this_question}
- missing_slots: {missing_slots_inline}
- what_i_want_to_hear: {what_i_want_to_hear_inline}
- risk_level: {risk_level}

---

### 第 2 轮 · ...
（同上）

</details>
```

**作弊模式 OS 默认带上**（已确认）：差异化证据。

### 9.4 UI 入口

- 报告页右上角「导出为 Markdown」按钮
- 个人主页训练时间线每行右侧「下载 .md」icon
- session 状态非 `reviewed` 时按钮置灰

---

## 10. F7 个人主页 dashboard

### 10.1 入口

- 现有 5 视图（home / onboarding / material / interview / report）右上角持久化「我的训练」按钮
- `localStorage.userId` 为空（理论上不会，因为启动就生成）→ 按钮置灰
- 已有 session（`user_profile.total_sessions > 0`）→ 按钮显示红点提示

### 10.2 Layout（ASCII mockup）

```
┌─────────────────────────────────────────────────────┐
│  ProjectProbe       [我的训练 ●]  [回首页]  [深色]   │
├─────────────────────────────────────────────────────┤
│  我的训练记录 (anonymous · 本机 ID: 7f3a-b8c2)        │
│  ┌──────────┬───────────┬──────────┐                │
│  │ 总 session│ 平均分    │ 训练天数  │                │
│  │   12     │ 76 / 100  │   5      │                │
│  └──────────┴───────────┴──────────┘                │
│                                                     │
│  ▼ 最常薄弱的槽位                                     │
│  baseline       ████████████  8 次                   │
│  个人贡献       ██████        5 次                   │
│  错误分析       ████          3 次                   │
│                                                     │
│  ▼ 训练时间线                                         │
│  ┌──────────────────────────────────────────────┐   │
│  │ 2026-05-12 18:30  [保研] 财会 Agent 项目      │   │
│  │ 总分 68 / 弱点: baseline, 错误分析            │   │
│  │ [重练 baseline] [重练 错误分析] [下载 .md]    │   │
│  ├──────────────────────────────────────────────┤   │
│  │ 2026-05-11 21:15  [求职] 推荐系统项目         │   │
│  │ 总分 82 / 弱点: 个人贡献                      │   │
│  │ [重练 个人贡献] [下载 .md]                    │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ▼ 训练过的项目                                       │
│  • 财会 Agent 项目（4 次）— [再来一次]                │
│  • 推荐系统项目（2 次）— [再来一次]                   │
└─────────────────────────────────────────────────────┘
```

### 10.3 Sections（自上而下）

#### 10.3.1 Hero stats（3 张卡片）
- 总 session 数
- 平均分
- 训练天数（distinct date count from `sessions[].created_at`）

#### 10.3.2 最常薄弱的槽位（柱状图）
- 取 `recurring_weaknesses` top 5
- 横向柱状图，纯 CSS（`<div style="width: ${count*15}px">`）
- max bar = 最大 count，其它按比例缩放

#### 10.3.3 训练时间线
- 倒序展示 `sessions[]`（最新在最上）
- 每行：日期 + target tag + project_summary_short + 总分 + 弱点 inline tags + 操作按钮
- 操作按钮：每个 weakness_tag 一个「重练 X」按钮 + 「下载 .md」
- 「重练 X」按钮点击 → POST `/api/interviewer/replay` → 跳转到 interview 视图（replay 模式）
- 重练产生的 session 在时间线中显示为子项缩进，prefix `↳ 重练 baseline`

#### 10.3.4 训练过的项目
- 取 `projects[]` 去重
- 每条显示「(N 次)」表示该项目被训练过几次
- 「再来一次」按钮 → 跳转到 onboarding，project_summary 预填

### 10.4 视觉

- 沿用 v2 深色主题 + 现有 CSS 变量（`web/index.html` 内 `:root` 已定义）
- 不引入新依赖（无 Chart.js / D3）
- 柱状图纯 CSS：
  ```css
  .bar { height: 18px; background: var(--accent); border-radius: 2px; }
  ```
- 浅色主题（v2 已加 toggle）兼容：使用现有 `--bg` / `--fg` / `--accent` 变量

### 10.5 新视图

- `web/index.html` 加 `<div id="view-profile" class="view hidden">...</div>`
- `web/app.js` 加 `renderProfile(userProfile)` 函数 + 路由 `state.view = "profile"` 切换
- 顶部「我的训练」按钮在所有视图共享 header 内（已有 header）

### 10.6 空 state

- `total_sessions === 0` → 显示「还没训练过，去[首页]开始第一次训练」
- 不显示空的 hero stats / 时间线（避免 0/0 NaN 显示）

---

## 11. 测试策略

### 11.1 新 unit tests

`tests/unit/`：

- **test_user_profile.py**
  - `add_session_meta` 累计：sessions append / total +1 / average 重算 / weakness count 累加 / projects 去重
  - 空 profile load → 默认空对象（不 raise）
  - canonicalization: "Baseline" / "baseline " → 同一 key
- **test_replay_packet.py**
  - `build_replay_packet` 保留原 packet 所有字段 + 加 replay_mode/focus_slots/parent_session_id
  - INTERVIEWER_REPLAY_PROMPT_INJECT 渲染 focus_slots / state 占位符
- **test_replay_coverage.py**
  - 闭式覆盖度：focus=[a,b,c]、turn1.covered=[a,b]、turn2.covered=[c] → coverage=1.0
  - 部分覆盖：focus=[a,b,c]、turn.covered=[a] → coverage≈0.333
  - canonicalization：focus=["Baseline"]、covered=["baseline"] → coverage=1.0
  - 空 focus → 0.0（不抛 ZeroDivisionError）
- **test_resume_iterate.py**
  - `iterate_resume` LLM mock：still_missing 递减
  - `is_good_enough` 当 still_missing 空时为 True
  - `iteration_index` 递增（基于 len(revision_history)+1）
- **test_export_markdown.py**
  - 8 段全部存在
  - UTF-8 中文 round-trip
  - `<details>` 折叠对话日志
  - interviewer_os 5 字段全部出现
  - revision_history 非空时第 5 段含历次迭代

### 11.2 新 endpoint tests

`tests/server/test_endpoints_plan2.py`：每个新 endpoint 1 happy + 1 negative：

| Endpoint | Happy | Negative |
|---|---|---|
| `GET /api/users/{user_id}/profile` | 已有 sessions → 返回聚合 | 不存在的 user_id → 返回空 profile（不是 404） |
| `POST /api/interviewer/replay` | 合法 parent + focus → 启动 replay | parent_session_id 不存在 → 404 |
| `POST /api/interviewer/replay/finish` | replay 完成 → mini-report | session 非 replay → 400 |
| `POST /api/coach/resume_iterate` | 合法 session + revised → ResumeRevision | session_id 不存在 → 404 |
| `GET /api/sessions/{session_id}/export.md` | reviewed session → markdown 流 | session 非 reviewed → 409；不存在 → 404 |

### 11.3 新 integration test

`tests/server/test_plan2_loop.py`：`onboard → plan → start → next×3 → review → resume_iterate → replay → mini-report → export.md` 全链路（mock LLM）。

### 11.4 维护现有

v2 现有 59 tests 必须继续 pass。v2 schemas 加默认字段 + endpoints 加可选 user_id 应当向后兼容；如有 break 视为 spec 实施 bug。

---

## 12. 风险 + 兜底

| 风险 | 兜底 |
|---|---|
| 已部署 v2 在线，老 session JSON 缺 user_id 字段 | Pydantic schema 全部新字段加默认值；老 session 自动以 anonymous 身份进入新 dashboard |
| 重练 mini-report slot 名拼写不一致 | `coach.py` 提供 slot canonicalization（lowercase + strip）；所有比较走 canonical key |
| Markdown 导出时 session 还在进行 | 后端检查 session 状态，非 reviewed → 返回 409 + 前端按钮置灰 |
| F4 简历多轮 token 累积 | 每次只传原始 + 上一版 missing + 当前 revised，不累积 revision_history |
| 重练 prompt 注入失效，Interviewer 偏离 focus_slots | 加额外的 turn-level 检查：若 turn.covered_slots 完全不含 focus_slots，server 端记 warning + 前端显示提示 |
| user_profile.json 写入并发冲突 | SessionStore 加 asyncio.Lock per user_id；写入用 atomic rename（`tmp` → `final`） |
| dashboard 加载慢（profile.sessions 过多） | profile.sessions 显示前 20 条 + "加载更多"按钮；后端无限制 |
| 用户清浏览器缓存 → 历史全丢 | 这是设计意图（无登录），UI 写明「本地存储，清缓存即重置」 |

---

## 13. v2 兼容性

### 13.1 schema 兼容

- 所有新字段加默认值（`= "anonymous"` / `= []` / `= None` / `= False`）
- v2 现有 session JSON 文件 / API 响应应能直接加载新 schema 不报错

### 13.2 endpoint 兼容

- 现有 6 个 POST endpoint 加可选 `user_id`：v2 客户端不传 → fallback `anonymous`
- 现有 GET `/api/healthz` 不变

### 13.3 前端兼容

- 启动时 localStorage 自动生成 user_id（无破坏）
- 老用户首次访问 v3 后被分配 anonymous user_id；之前的 v2 session 不会自动归到他名下（v2 没有 user_id 概念）

### 13.4 部署兼容

- 新增 `data/users/` 目录，`SessionStore` 启动时自动 mkdir
- 不需要数据库迁移
- 不改 nginx / systemd / SSL

---

## 14. 实施依赖图

```
schemas.py (Plan2 新字段)
   ↓
store.py (UserProfile + list_user_sessions + update_user_profile)
   ↓
   ├── coach.py (compute_replay_coverage / iterate_resume / summarize_replay)
   ├── interviewer.py (replay_mode 注入 prompt)
   └── export.py (新模块: render_markdown)
   ↓
server/main.py (5 新 endpoint + 6 老 endpoint 加 user_id)
   ↓
web/app.js + web/index.html (新视图 view-profile + UI 改动)
```

实施顺序：`schemas → store → coach/interviewer/export 并行 → server → web`。

详细 task 拆分由 writing-plans skill 在下一步起草，输出到 `docs/plans/Plan2-long-term-training.md`（或拆为 Plan2A/B/C，由 writing-plans 决定）。

---

## 15. 评分自检（每个 feature 必答）

> 「相比于直接使用 ChatGPT，这个产品真的能更好地帮助一个学生更好地准备面试。」

| feature | 答案 |
|---|---|
| F1 持久化 | ChatGPT 跨 session 不记得你；ProjectProbe 记得你的项目 / 弱点 / 历史训练 |
| F2 一键重练 | ChatGPT 没有"针对昨天弱点的下一轮训练"机制；ProjectProbe 把弱点 → 下一轮 focus |
| F4 简历多轮 | ChatGPT 改完简历不验证；ProjectProbe 评估 missing_evidence 是否被覆盖 |
| F5 Markdown 导出 | ChatGPT 输出无结构；ProjectProbe 给完整 8 段含面试官 OS 的复盘文档 |
| F7 个人主页 | ChatGPT 无 dashboard；ProjectProbe 让用户看见自己的弱点演化 + 训练量 |

每条都过关。
