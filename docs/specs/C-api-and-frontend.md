# Spec C — API + Frontend

> 起草日期：2026-05-10
> 父文档：[../overview.md](../overview.md)
> 范围：FastAPI 路由层 + SSE + 前端单页 vanilla JS UI
> 上游依赖：[Spec A](A-backend-agents.md) 全部 services；[Spec B](B-question-bank.md) QuestionBank

---

## 1. 模块边界

```
server/
└── main.py             FastAPI 入口；8 个 endpoint；lifespan；SSE
                        （服务模块化在 services/ 内，main 只做路由 + 编排）

web/
├── index.html          单页骨架（5 个视图通过 #section 切换）
├── app.js              所有交互逻辑 + fetch + SSE 接收
└── styles.css          chat-like + report-like 双视图

deploy/
├── aiic-chat.service           systemd unit（沿用 v1）
└── nginx-aiic.location.conf    nginx location 模板（无需改动）
```

**v1 复用**：`pixi.toml` 的 fastapi/uvicorn/httpx/python-dotenv 直接复用。`pytest.ini` 沿用。

---

## 2. 8 个 endpoint 详细规格

所有 endpoint 前缀 `/api/`。请求 / 响应均为 JSON（除 SSE）。

### 2.1 GET /api/healthz

**用途**：主办方 SSH 登录后 `curl localhost/api/healthz` 验证服务在线。

**Response 200**:
```json
{
  "status": "ok",
  "version": "v2-mvp",
  "commit_hash": "<git rev-parse --short HEAD at startup>",
  "deploy_time": "2026-05-10T17:30:00+08:00",
  "provider": "deepseek"
}
```

`commit_hash` 与 `deploy_time` 在 lifespan startup 时取一次 cache 起来。

### 2.2 POST /api/coach/onboard

**用途**：Coach 多轮澄清需求。

**Request**:
```json
{
  "user_message": "我准备保研人工智能创新中心，项目是财会 Agent...",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Response 200** (need more info):
```json
{
  "need_more_info": true,
  "followup_questions": ["你这次主要是为了准备保研复试还是 AI 岗位面试？"],
  "user_model": null,
  "recommended_packet": null
}
```

**Response 200** (info complete):
```json
{
  "need_more_info": false,
  "followup_questions": [],
  "user_model": { ... UserModel ... },
  "recommended_packet": { ... InterviewPacket ... }
}
```

**Errors**:
- 400: `user_message` 为空
- 502: LLM 反复失败（fallback 已用尽）

### 2.3 POST /api/profile/parse

**用途**：从用户粘贴的项目原文抽取结构化项目画像。Onboarding 完成后调用。

**Request**:
```json
{
  "raw_project_text": "我做了一个面向中小企业财务部门的 AI 财务助理..."
}
```

**Response 200**:
```json
{
  "project_summary": "AI 财务助理：解析 Excel/PDF/发票...",
  "technical_keywords": ["LLM", "OCR", "公式生成"],
  "possible_weaknesses": ["缺少 baseline 对比", "异常 case 覆盖率不明"],
  "likely_followup_directions": ["公式验证方法", "脱敏架构具体实现"]
}
```

**Errors**:
- 400: 文本过短（<50 字符）

### 2.4 POST /api/coach/plan

**用途**：基于 UserModel + 项目画像生成训练计划 + InterviewPacket。

**Request**:
```json
{
  "user_model": { ... },
  "project_summary": "..."
}
```

**Response 200**:
```json
{
  "training_plan": { ... TrainingPlan ... },
  "interview_packet": { ... InterviewPacket ... }
}
```

### 2.5 POST /api/interviewer/start

**用途**：开始一场面试，返回第一问。

**Request**:
```json
{
  "interview_packet": { ... },
  "user_model": { ... }
}
```

**Response 200**:
```json
{
  "session_id": "abc123...",
  "state": "S1_motivation",
  "question": "你是怎么发现这个痛点真实存在的？...",
  "interviewer_os": { ... },
  "focus_slots": ["pain_real", "target_user"]
}
```

### 2.6 POST /api/interviewer/next

**用途**：用户回答后获取下一问。

**Request**:
```json
{
  "session_id": "abc123",
  "answer": "我们做了几次用户访谈..."
}
```

**Response 200**:
```json
{
  "turn": { ... InterviewTurn ... },
  "should_continue": true,
  "next_state": "S1_motivation"
}
```

`should_continue=false` 时前端显示「面试结束」按钮，跳转 review。

**Errors**:
- 404: session 不存在或已过期（`{"error": "session_expired", "message": "请重新开始训练"}`)

### 2.7 POST /api/coach/review

**用途**：面试结束后生成复盘报告。

**Request**:
```json
{
  "session_id": "abc123"
}
```

**Response 200**: 完整 `EvaluationReport`

**Errors**:
- 404: session 不存在
- 400: session 尚未结束（state != DONE 且 turns < 6）

### 2.8 SSE 变体（可选 P1）

P0 所有 endpoint 走普通 JSON 响应。如果 LLM 调用让响应延迟超过 5s 影响体验，P1 升级 `interviewer/next` 和 `coach/review` 为 SSE 变体（同 path 加 `Accept: text/event-stream` header），让前端逐 token 展示。

P0 不做 SSE，但前端代码结构要预留 `streamMode` 开关（避免 P1 改动大）。

---

## 3. SSE 协议（仅 P1，但留接口）

事件格式（复用 v1 经验）：

```
event: token
data: {"text": "..."}

event: done
data: {"turn": { ... InterviewTurn ... }}

event: error
data: {"message": "..."}
```

**v1 教训**（来自 CLAUDE.md「v1 历史 gotchas」）：
- `httpx.InvalidURL` 不继承 `httpx.HTTPError` → generator 兜底用 `except Exception`
- 200 已发出后异常 = client 收到 truncated stream 无 error 帧 → 兜底必发 `event: error`
- MiMo 双流过滤经验暂不适用（DeepSeek 无 reasoning_content）；但解析逻辑保留容忍

---

## 4. FastAPI 项目结构（server/main.py）

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from services import coach, interviewer
from services.store import SessionStore
from services.question_bank import QuestionBank

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = SessionStore()
    app.state.bank = QuestionBank()
    app.state.commit_hash = _git_short_hash()
    app.state.deploy_time = datetime.now(timezone(timedelta(hours=8))).isoformat()
    yield
    # no cleanup needed

app = FastAPI(lifespan=lifespan)

# 静态文件挂载（web/ → /）
app.mount("/web", StaticFiles(directory="web"), name="web")

@app.get("/")
async def root():
    return FileResponse("web/index.html")

@app.get("/api/healthz")
async def healthz():
    return {
        "status": "ok",
        "version": "v2-mvp",
        "commit_hash": app.state.commit_hash,
        "deploy_time": app.state.deploy_time,
        "provider": "deepseek",
    }

# ... 其余 7 个 endpoint
```

**Auth**：不做 in-app auth。Basic Auth 由 nginx 透传，FastAPI 不解析 Authorization header（[`docs/deployment.md`](../deployment.md)）。

**CORS**：不需要（前后同源，nginx 反代）。

---

## 5. 前端页面 state machine

单页 SPA，5 个视图通过 `#sectionName` 显隐：

```
state machine:
  HOME → ONBOARDING → MATERIAL_INPUT → INTERVIEW → REPORT
                            ↑              ↓
                      （示例项目跳过）  （DONE 跳 REPORT）
```

切换函数：

```js
function switchView(name) {
  // name in {"home", "onboarding", "material", "interview", "report"}
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  document.querySelector(`#view-${name}`).classList.remove("hidden");
  window.scrollTo(0, 0);
}
```

全局状态用单个 `state` 对象（不引入 framework）：

```js
const state = {
  history: [],          // onboarding 对话历史
  user_model: null,
  packet: null,
  session_id: null,
  current_state: null,  // InterviewStage
  current_question: null,
  turns: [],            // for transcript display
  report: null,
};
```

---

## 6. 前端 5 个视图

### 6.1 HOME

```
┌────────────────────────────────────────────────┐
│ ProjectProbe                            [aiic] │
│                                                │
│ 不是再问你一堆八股题，                         │
│ 而是把你的项目追问到讲明白。                   │
│                                                │
│ [开始训练]  [使用示例项目体验]                 │
└────────────────────────────────────────────────┘
```

副文案：「ProjectProbe 模拟 AI 保研复试 / 岗位面试，对你的项目进行连续追问，结束后告诉你：哪里答空了、哪里容易被追杀、简历应该怎么改、下一轮该练什么。」

### 6.2 ONBOARDING

chat-like UI：左侧 Coach 头像 + 消息气泡，右侧用户气泡。底部输入框 + 提交。

```
┌────────────────────────────────────────┐
│ Coach: 你这次主要是为了准备保研，还是  │
│        AI 岗位面试？                   │
│                                        │
│                       User: 保研复试   │
│                                        │
│ Coach: 好。你想报考的实验室 / 老师是   │
│        哪个方向？                      │
│ ...                                    │
│                                        │
│ [输入框..........................][发送] │
└────────────────────────────────────────┘
```

每次提交：`POST /api/coach/onboard` with `{user_message, history}`. 收到 `need_more_info=true` 继续，否则切到 MATERIAL_INPUT。

### 6.3 MATERIAL_INPUT

```
┌────────────────────────────────────────┐
│ 把你的项目经历粘贴进来                 │
│                                        │
│ 当前版本为了保证面试质量，建议先粘贴   │
│ 1-3 段最重要的项目经历。               │
│ PDF / Word / 图片 → 用 ChatGPT 等转    │
│ 文本后再提交。                         │
│                                        │
│ [大文本框..........................]   │
│                                        │
│ [使用示例项目（财会 Agent）] [开始面试] │
└────────────────────────────────────────┘
```

「使用示例项目」按钮：填入 hardcode 的财会 Agent 项目文本（来自 [overview.md §14.2](../overview.md#142)）。

「开始面试」：先 `POST /api/profile/parse` → 拿到 `project_summary`，再 `POST /api/coach/plan` → 拿到 `interview_packet`，然后 `POST /api/interviewer/start` → 切到 INTERVIEW。

### 6.4 INTERVIEW

```
┌──────────────────────────────────────────────────┐
│ 当前阶段: S4 实验验证   重点: baseline / 指标   │
│ ──────────────────────────────────────────────── │
│ 面试官:                                          │
│   你说 AI 不接触真实数值，只生成公式。那么 AI  │
│   如何在不知道真实数值的情况下判断公式是正确    │
│   的？你如何设计测试样例来验证公式生成结果？    │
│                                                  │
│ 你:                                              │
│ [大文本框..............................][提交]  │
│                                                  │
│ ─── 上一轮反馈 ───                              │
│ 你的回答提到了样例数据，但没说明样例如何构造... │
│ 缺失槽位: baseline, 异常 case, 测试样例设计    │
│                                                  │
│ [▶ 偷看面试官脑回路（作弊模式）]               │
└──────────────────────────────────────────────────┘
```

提交：`POST /api/interviewer/next` → 拿到 turn → 渲染 feedback + missing_slots，append 到对话；`should_continue=false` 时按钮文案变「结束面试 → 看报告」。

### 6.5 REPORT

```
┌────────────────────────────────────────────────────┐
│ 训练报告                          总分: 67 / 100   │
│ ────────────────────────────────────────────────── │
│ 概述: 你的项目主线讲得清晰，但实验验证部分薄弱... │
│                                                    │
│ ▼ 关键证据 (3 处)                                  │
│   • 你说: "我们用一些样例数据测试公式"             │
│     问题: 没说样例如何构造、覆盖哪些异常          │
│     建议: 显式提 baseline + 异常 case 覆盖率      │
│   ...                                              │
│                                                    │
│ ▼ 最危险的 3 个追问                                │
│   1. 你的 baseline 具体是什么？                    │
│   2. 异常 case 覆盖率怎么验证？                    │
│   3. 你团队里你独立完成的部分边界？                │
│                                                    │
│ ▼ 简历改写                                         │
│   原文: 我做了一个 AI 财务助理...                  │
│   改写: 我设计并实现了一个面向中小企业的...       │
│   仍缺: baseline 对比 / 异常 case 数据             │
│                                                    │
│ ▼ 下一轮训练计划                                   │
│   推荐: 普通项目面 → 重练 S4                       │
│   • Step 1: 补 baseline ...                       │
│   • Step 2: 设计异常 case ...                     │
│                                                    │
│ ▼ 今日高价值 bug 收集报告                          │
│   你今天暴露了 3 个复试雷区: baseline / 公式验证 │
│   / 异常 case。按普通复习法这叫 "我什么都不会"...│
│                                                    │
│ [一键重练 S4 (薄弱项)]  [回到首页]                │
└────────────────────────────────────────────────────┘
```

「一键重练」P0 实现：直接跳回 ONBOARDING 并 pre-fill 之前的 user_model（前端 state 缓存）。完整重练新 session（不复用旧 session_id）。

---

## 7. 作弊模式 UI

### 默认收起 → 按钮展开

```
[▶ 偷看面试官脑回路（作弊模式）]
   ↓ 点击展开 ↓
┌─────────────────────────────────────┐
│ 🔍 面试官内心 OS         风险: 高   │
│ ─────────────────────────────────── │
│ 真正担心: 候选人可能只讲了架构愿景，│
│           没有真实验证闭环。        │
│                                     │
│ 为什么追问: 公式验证是这个项目能否  │
│             落地的核心。            │
│                                     │
│ 缺失槽位:                           │
│   • 测试样例设计                    │
│   • 异常 case                       │
│   • baseline                        │
│                                     │
│ 想听到的:                           │
│   • 如何构造样例数据                │
│   • 如何覆盖异常 case               │
│   • 如何设计 baseline               │
└─────────────────────────────────────┘
```

`risk_level` 用色块：低=绿、中=黄、高=红。

CSS：`#cheat-panel.expanded` 显示，否则 `display: none`。点击 toggle 一个 class 即可，不引入动画库。

---

## 8. Demo 路径优化（保 wow moment 流畅）

### 8.1 「使用示例项目体验」分支

点击后的快速路径：
1. 不走 ONBOARDING（直接 hardcode user_model: target=求职、target_program="字节 AI Lab 实习"）
2. 切到 MATERIAL_INPUT 并 pre-fill 财会 Agent 项目文本
3. 「开始面试」按钮文案改为「直接开始（已加载示例）」

### 8.2 第一问保稳

`POST /api/interviewer/start` 在 demo 模式下**绕过** LLM，直接返回 hardcode 的高质量 S1 题（避免 LLM 抽风让 demo 第一秒崩）：

```python
# server/main.py
DEMO_FIRST_QUESTION = {
    "session_id": "<新建>",
    "state": "S1_motivation",
    "question": "你是怎么发现这个财务痛点真实存在的？你访谈过几个真实用户吗？",
    "interviewer_os": { ... 高质量 hardcode os ... },
    "focus_slots": ["pain_real", "target_user"],
}
```

通过 query string `?demo=1` 触发。

### 8.3 用户故意答空泛 → 必然识别 missing_slots

P0 不做 hardcode 第二问（依赖真实 LLM）。但在 prompt 里强约束：「如果回答 ≤30 字符或没有具体数字 / 实例，score 必须 < 40，missing_slots 必须 ≥3 个」。

实测如果不稳定，临时 hardcode 第二问的 LLM 输出（demo 时强 ngrok / curl 录制）。

### 8.4 整体 demo 路径打磨节点

实施完成后必跑一次完整 demo 回放：HOME → 示例项目 → 第 1 问（hardcode）→ 故意答空（手动）→ 第 2 问（LLM）→ 答 1-2 轮真实回答 → 结束 → 报告。卡顿点全部记录到 [`progress/Plan1-report.md`]。

---

## 9. 部署与启动

### 9.1 本地启动

```bash
pixi install   # 沿用 pixi.toml；新依赖按需 pixi add
pixi run serve   # uvicorn server.main:app --reload --host 127.0.0.1 --port 8000
```

`pixi.toml` task 沿用 v1：

```toml
[tasks]
serve = "uvicorn server.main:app --reload --host 127.0.0.1 --port 8000"
serve-prod = "uvicorn server.main:app --host 127.0.0.1 --port 8000 --workers 1"
test = "pytest -v"
synthesize-questions = "python scripts/synthesize_questions.py --target-count 60"
```

### 9.2 服务器部署

复用 v1 systemd unit `aiic-chat.service`（监听 127.0.0.1:8000）。新代码 push 后：

```bash
# 服务器
cd /opt/aiic-project   # （部署目录沿用 v1；如不同实施时确认）
git pull
pixi install
sudo systemctl restart aiic-chat
curl -s -u aiic:<PWD> https://aiic.fomalhaut647.com/api/healthz | jq .
```

nginx 配置无需改动（`location /` 反代到 :8000，`proxy_buffering off` 透传 SSE 已配）。

---

## 10. 实施顺序

```
Step 1: server/main.py 骨架 + healthz + lifespan + 静态文件挂载  （~30min）
Step 2: web/index.html + styles.css 5 个视图骨架                 （~45min）
Step 3: web/app.js 状态机 + switchView + state object             （~30min）
Step 4: 接入 8 个 endpoint 逐个 fetch                              （~2h；与 Spec A 实施并行）
Step 5: 作弊模式 UI + 报告页 component                            （~1h）
Step 6: demo 路径优化（hardcode 第一问 + 示例项目分支）            （~30min）
Step 7: 端到端 demo 回放 + 修 bug                                  （~1h）
```

总耗时 ~6h；可由 1 个 implementer 完成（与 [Spec A](A-backend-agents.md) 后端实施并行进行）。Step 4 的每个 endpoint 接入可以 fan-out 给多个 implementer 但不划算（前端共享 state object）。
