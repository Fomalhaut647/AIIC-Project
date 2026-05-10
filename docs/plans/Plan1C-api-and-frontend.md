# AIIC v2 Plan1C — API + Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 [Spec C](../specs/C-api-and-frontend.md)：FastAPI 路由层（8 个 endpoint）+ vanilla JS 单页前端（5 个视图 + 作弊模式）+ demo 路径优化 + 部署到 `aiic.fomalhaut647.com`。

**Architecture:** server/main.py 编排 services/，web/ 用 fetch + 简单 state object 驱动 5 视图。复用 v1 systemd unit + nginx。

**Tech Stack:** FastAPI / uvicorn / vanilla HTML/CSS/JS / pixi / systemd / nginx

**Pre-conditions:**
- Plan1A Task A6 / A7 / A8 / A10 / A11 已完成（services.coach + services.interviewer 可调）
- Plan1B Task B2 已完成（services.question_bank.QuestionBank 真实可用），或可用 Plan1A Task A10 的 stub
- 服务器 SSH + nginx + Basic Auth 已就绪（v1 部署遗产，详见 [docs/deployment.md](../deployment.md)）

**Spec coverage:**

| Spec C 节 | Plan task |
|---|---|
| §1 模块边界 | C0 / C1 |
| §2 8 个 endpoint | C2 / C3 / C4 |
| §3 SSE 协议（P1） | （不在 P0 范围） |
| §4 FastAPI 项目结构 | C1 |
| §5 前端 state machine | C6 |
| §6 5 个视图 | C5 / C7 / C8 |
| §7 作弊模式 UI | C9 |
| §8 Demo 路径优化 | C10 |
| §9 部署 | C12 |

---

### Task C0: pixi.toml task 与依赖准备

**Files:**
- Modify: `pixi.toml`

- [ ] **Step 1: 检查并补全 [tasks] 节**

```bash
grep -E "^(serve|test|synthesize-questions)" pixi.toml || echo "MISSING TASKS"
```

- [ ] **Step 2: 编辑 pixi.toml 的 [tasks]**

确保以下 task 都存在：

```toml
[tasks]
serve = "uvicorn server.main:app --reload --host 127.0.0.1 --port 8000"
serve-prod = "uvicorn server.main:app --host 127.0.0.1 --port 8000 --workers 1"
test = "pytest -v"
synthesize-questions = "python scripts/synthesize_questions.py"
```

- [ ] **Step 3: Smoke**

```bash
pixi run python -c "import fastapi; import uvicorn; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit (如有改动)**

```bash
git add pixi.toml
git commit -m "chore(pixi): ensure serve/serve-prod/test/synthesize tasks defined"
```

---

### Task C1: server/main.py 骨架 + healthz + lifespan + 静态挂载

**Files:**
- Create: `server/__init__.py`
- Create: `server/main.py`
- Test: `tests/test_healthz.py`

- [ ] **Step 1: 创建 server/__init__.py 空文件**

```bash
mkdir -p server
touch server/__init__.py
```

- [ ] **Step 2: 写 tests/test_healthz.py**

```python
from fastapi.testclient import TestClient
from server.main import app


def test_healthz_returns_ok():
    with TestClient(app) as client:
        resp = client.get("/api/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["provider"] == "deepseek"
        assert "commit_hash" in body
        assert "deploy_time" in body
```

- [ ] **Step 3: Run test → 应失败**

```bash
pixi run pytest tests/test_healthz.py -v
```

Expected: ImportError on `server.main`.

- [ ] **Step 4: 写 server/main.py 骨架**

```python
"""ProjectProbe v2 — FastAPI 入口。"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.store import SessionStore
from services.question_bank import QuestionBank


def _git_short_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = SessionStore()
    app.state.bank = QuestionBank()
    app.state.commit_hash = _git_short_hash()
    cn_tz = timezone(timedelta(hours=8))
    app.state.deploy_time = datetime.now(cn_tz).isoformat(timespec="seconds")
    yield


app = FastAPI(lifespan=lifespan, title="ProjectProbe v2")

# 静态资源（CSS/JS）
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def root():
    if (WEB_DIR / "index.html").exists():
        return FileResponse(str(WEB_DIR / "index.html"))
    return {"message": "ProjectProbe v2 — frontend not built"}


@app.get("/api/healthz")
async def healthz():
    return {
        "status": "ok",
        "version": "v2-mvp",
        "commit_hash": app.state.commit_hash,
        "deploy_time": app.state.deploy_time,
        "provider": "deepseek",
    }
```

- [ ] **Step 5: Run test → 应通过**

```bash
pixi run pytest tests/test_healthz.py -v
```

Expected: 1 PASS.

- [ ] **Step 6: Smoke 真启动**

```bash
pixi run serve &
SERVER_PID=$!
sleep 2
curl -s http://127.0.0.1:8000/api/healthz | python -m json.tool
kill $SERVER_PID 2>/dev/null
```

Expected: 输出 healthz JSON, status="ok".

- [ ] **Step 7: Commit**

```bash
git add server/ tests/test_healthz.py
git commit -m "feat(server): scaffold fastapi app with healthz + lifespan + static mount"
```

---

### Task C2: server/main.py — Coach endpoints (onboard / parse / plan)

**Files:**
- Modify: `server/main.py`

- [ ] **Step 1: 在 server/main.py 末尾追加**

```python
from services.schemas import (
    UserModel, InterviewPacket, OnboardResult, CoachPlanResult,
)
from services import coach
from services.llm import call_deepseek
from services.prompts import PROFILE_PARSE_SYSTEM


# --- /api/coach/onboard ---

class _OnboardReq(BaseModel):
    user_message: str
    history: list[dict] = []


@app.post("/api/coach/onboard", response_model=OnboardResult)
async def api_coach_onboard(body: _OnboardReq):
    if not body.user_message.strip():
        raise HTTPException(400, "user_message empty")
    return await coach.onboard(body.user_message, body.history)


# --- /api/profile/parse ---

class _ParseReq(BaseModel):
    raw_project_text: str


class _ParseResp(BaseModel):
    project_summary: str
    technical_keywords: list[str]
    possible_weaknesses: list[str]
    likely_followup_directions: list[str]


@app.post("/api/profile/parse", response_model=_ParseResp)
async def api_profile_parse(body: _ParseReq):
    if len(body.raw_project_text) < 50:
        raise HTTPException(400, "text too short (need >=50 chars)")
    fallback = _ParseResp(
        project_summary=body.raw_project_text[:200],
        technical_keywords=[], possible_weaknesses=[],
        likely_followup_directions=[],
    )
    return await call_deepseek(
        [
            {"role": "system", "content": PROFILE_PARSE_SYSTEM},
            {"role": "user", "content": body.raw_project_text},
        ],
        response_schema=_ParseResp,
        temperature=0.3, fallback=fallback,
    )


# --- /api/coach/plan ---

class _PlanReq(BaseModel):
    user_model: UserModel
    project_summary: str


@app.post("/api/coach/plan", response_model=CoachPlanResult)
async def api_coach_plan(body: _PlanReq):
    return await coach.plan(body.user_model, body.project_summary)
```

- [ ] **Step 2: Smoke**

```bash
pixi run serve &
SERVER_PID=$!
sleep 2
curl -s -X POST http://127.0.0.1:8000/api/coach/onboard \
  -H 'Content-Type: application/json' \
  -d '{"user_message": "我准备保研人工智能创新中心"}' | head -c 300
echo
kill $SERVER_PID 2>/dev/null
```

Expected: 输出 OnboardResult JSON 含 followup_questions 或 user_model.

- [ ] **Step 3: Commit**

```bash
git add server/main.py
git commit -m "feat(api): add coach onboard / profile parse / coach plan endpoints"
```

---

### Task C3: server/main.py — Interviewer endpoints (start / next)

**Files:**
- Modify: `server/main.py`

- [ ] **Step 1: 在 server/main.py 末尾追加**

```python
from services.schemas import InterviewTurn, InterviewStage
from services import interviewer


# --- /api/interviewer/start ---

class _StartReq(BaseModel):
    interview_packet: InterviewPacket
    user_model: UserModel


class _StartResp(BaseModel):
    session_id: str
    state: InterviewStage
    question: str
    interviewer_os: dict  # InterviewerOS — 序列化时直接 dict
    focus_slots: list[str]


@app.post("/api/interviewer/start", response_model=_StartResp)
async def api_interviewer_start(body: _StartReq):
    sid, turn = await interviewer.start(
        body.interview_packet, body.user_model,
        app.state.bank, app.state.store,
    )
    return _StartResp(
        session_id=sid,
        state=turn.state,
        question=turn.question,
        interviewer_os=turn.interviewer_os.model_dump(mode="json"),
        focus_slots=body.interview_packet.focus_slots,
    )


# --- /api/interviewer/next ---

class _NextReq(BaseModel):
    session_id: str
    answer: str


class _NextResp(BaseModel):
    turn: InterviewTurn
    should_continue: bool
    next_state: InterviewStage


@app.post("/api/interviewer/next", response_model=_NextResp)
async def api_interviewer_next(body: _NextReq):
    from services.store import SessionNotFound
    try:
        turn, cont, st = await interviewer.next_turn(
            body.session_id, body.answer,
            app.state.bank, app.state.store,
        )
    except SessionNotFound:
        raise HTTPException(404, detail={
            "error": "session_expired",
            "message": "请重新开始训练",
        })
    return _NextResp(turn=turn, should_continue=cont, next_state=st)
```

- [ ] **Step 2: Commit**

```bash
git add server/main.py
git commit -m "feat(api): add interviewer start + next endpoints"
```

---

### Task C4: server/main.py — Coach review endpoint

**Files:**
- Modify: `server/main.py`

- [ ] **Step 1: 在 server/main.py 末尾追加**

```python
from services.schemas import EvaluationReport


class _ReviewReq(BaseModel):
    session_id: str


@app.post("/api/coach/review", response_model=EvaluationReport)
async def api_coach_review(body: _ReviewReq):
    from services.store import SessionNotFound
    try:
        session = app.state.store.get(body.session_id)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    if not session.turns:
        raise HTTPException(400, "no turns to review")
    return await coach.review(session.user_model, session.packet, session.turns)
```

- [ ] **Step 2: Smoke 完整 e2e**

```bash
pixi run serve &
SERVER_PID=$!
sleep 2
SID=$(curl -s -X POST http://127.0.0.1:8000/api/interviewer/start \
  -H 'Content-Type: application/json' \
  -d '{
    "interview_packet": {"target":"保研","interviewer_style":"x","intensity":"中","project_summary":"AI 财会助理","focus_slots":["baseline"]},
    "user_model": {"id":"u","goal":"保研","target":"保研"}
  }' | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "session: $SID"
curl -s -X POST http://127.0.0.1:8000/api/interviewer/next \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"answer\":\"我们做了用户访谈\"}" | head -c 200
echo
kill $SERVER_PID 2>/dev/null
```

Expected: 输出 turn JSON 含 missing_slots 等.

- [ ] **Step 3: Commit**

```bash
git add server/main.py
git commit -m "feat(api): add coach review endpoint to close evaluation loop"
```

---

### Task C5: web/index.html — 5 视图骨架

**Files:**
- Create: `web/index.html`

- [ ] **Step 1: 写 web/index.html**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ProjectProbe — 项目深挖训练器</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<div id="app">

  <!-- HOME -->
  <section id="view-home" class="view">
    <header class="hero">
      <h1>ProjectProbe</h1>
      <p class="tagline">不是再问你一堆八股题，而是把你的项目追问到讲明白。</p>
      <p class="subtagline">
        模拟 AI 保研复试 / 岗位面试，对你的项目进行连续追问；
        结束后告诉你哪里答空了、哪里容易被追杀、简历应该怎么改、下一轮该练什么。
      </p>
      <div class="cta">
        <button id="btn-start">开始训练</button>
        <button id="btn-demo">使用示例项目体验</button>
      </div>
    </header>
  </section>

  <!-- ONBOARDING -->
  <section id="view-onboarding" class="view hidden">
    <h2>先让训练组长 Coach 了解你</h2>
    <div id="onboarding-history" class="chat"></div>
    <div class="composer">
      <textarea id="onboarding-input" placeholder="比如：我准备保研人工智能创新中心，项目是财会 Agent..."></textarea>
      <button id="btn-onboarding-send">发送</button>
    </div>
  </section>

  <!-- MATERIAL INPUT -->
  <section id="view-material" class="view hidden">
    <h2>把项目经历粘贴进来</h2>
    <p class="hint">建议先粘贴 1-3 段最重要的项目经历。PDF / Word / 图片请先用 ChatGPT / Kimi 等转成文本。</p>
    <textarea id="material-input" placeholder="项目原文..."></textarea>
    <div class="cta">
      <button id="btn-material-start">开始面试</button>
    </div>
  </section>

  <!-- INTERVIEW -->
  <section id="view-interview" class="view hidden">
    <div class="interview-banner">
      <span id="interview-stage">阶段加载中...</span>
      <span id="interview-focus"></span>
    </div>
    <div id="interview-question" class="question"></div>
    <div class="composer">
      <textarea id="interview-input" placeholder="你的回答..."></textarea>
      <button id="btn-interview-submit">提交</button>
    </div>
    <div id="interview-feedback" class="feedback hidden"></div>
    <button id="btn-cheat-toggle" class="cheat-toggle hidden">▶ 偷看面试官脑回路（作弊模式）</button>
    <div id="cheat-panel" class="cheat-panel hidden"></div>
    <button id="btn-finish" class="hidden">结束面试 → 看报告</button>
  </section>

  <!-- REPORT -->
  <section id="view-report" class="view hidden">
    <h2>训练报告</h2>
    <div id="report-content"></div>
    <div class="cta">
      <button id="btn-replay">一键重练（薄弱项）</button>
      <button id="btn-home">回到首页</button>
    </div>
  </section>

</div>
<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Smoke 浏览器加载**

```bash
pixi run serve &
SERVER_PID=$!
sleep 2
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/
kill $SERVER_PID 2>/dev/null
```

Expected: `200`.

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat(web): add 5-view html skeleton (home/onboarding/material/interview/report)"
```

---

### Task C6: web/styles.css — 基础样式

**Files:**
- Create: `web/styles.css`

- [ ] **Step 1: 写 web/styles.css**

```css
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft Yahei", sans-serif;
  background: #0d1117; color: #c9d1d9; line-height: 1.6;
}
#app { max-width: 880px; margin: 0 auto; padding: 24px; }
.view { animation: fadein 200ms ease; }
.view.hidden { display: none; }
.hidden { display: none; }
@keyframes fadein { from { opacity: 0; } to { opacity: 1; } }

/* HOME */
.hero { padding: 48px 0; text-align: center; }
.hero h1 { font-size: 56px; margin: 0 0 12px; color: #58a6ff; letter-spacing: -1px; }
.hero .tagline { font-size: 22px; margin: 16px 0; color: #f0f6fc; }
.hero .subtagline { color: #8b949e; max-width: 640px; margin: 0 auto 32px; }
.cta { margin-top: 24px; display: flex; gap: 12px; justify-content: center; }

/* Buttons */
button {
  padding: 12px 24px; font-size: 15px; border: 1px solid #30363d;
  background: #21262d; color: #f0f6fc; border-radius: 6px; cursor: pointer;
  transition: background 100ms;
}
button:hover { background: #30363d; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
#btn-start, #btn-material-start { background: #238636; border-color: #2ea043; }
#btn-start:hover, #btn-material-start:hover { background: #2ea043; }

/* Inputs */
textarea {
  width: 100%; min-height: 120px; padding: 12px;
  background: #161b22; color: #c9d1d9; border: 1px solid #30363d;
  border-radius: 6px; font: inherit; resize: vertical;
}
.composer { margin-top: 16px; }
.composer button { margin-top: 8px; float: right; }
.composer::after { content: ''; display: block; clear: both; }

/* Chat (onboarding) */
.chat { background: #161b22; padding: 16px; border-radius: 8px; min-height: 200px; }
.chat .msg { margin: 8px 0; }
.chat .msg.coach { color: #58a6ff; }
.chat .msg.user { color: #f0f6fc; text-align: right; }
.chat .msg .who { font-weight: bold; margin-right: 8px; }

/* Interview */
.interview-banner {
  background: #161b22; padding: 12px 16px; border-radius: 6px;
  margin-bottom: 16px; display: flex; justify-content: space-between;
  font-size: 14px; color: #8b949e;
}
#interview-stage { color: #f0f6fc; font-weight: bold; }
.question {
  font-size: 18px; padding: 20px; background: #0d1117;
  border-left: 3px solid #58a6ff; margin: 16px 0;
}
.feedback {
  background: #1c2128; padding: 12px 16px; border-radius: 6px;
  margin-top: 16px; font-size: 14px;
}
.feedback .miss { color: #f85149; font-weight: bold; }

/* Cheat mode */
.cheat-toggle {
  background: transparent; border: 1px dashed #58a6ff;
  color: #58a6ff; margin-top: 12px;
}
.cheat-panel {
  background: #161b22; padding: 16px; border-radius: 8px;
  margin-top: 12px; border-left: 3px solid;
}
.cheat-panel.risk-low { border-color: #3fb950; }
.cheat-panel.risk-mid { border-color: #d29922; }
.cheat-panel.risk-high { border-color: #f85149; }
.cheat-panel h3 { margin: 0 0 8px; font-size: 14px; color: #f0f6fc; }
.cheat-panel ul { padding-left: 20px; }

/* Report */
#report-content > section {
  background: #161b22; padding: 16px 20px; border-radius: 8px; margin: 12px 0;
}
#report-content h3 { margin: 0 0 8px; color: #58a6ff; font-size: 16px; }
#report-content .score { font-size: 48px; color: #f0f6fc; font-weight: bold; }
#report-content .resume-rewrite .original { opacity: 0.6; text-decoration: line-through; }
#report-content .resume-rewrite .rewritten { color: #3fb950; margin-top: 8px; }
#report-content .humor { background: #1c2128; padding: 16px; border-left: 3px solid #d29922; }
```

- [ ] **Step 2: 验证浏览器加载**

启动 `pixi run serve`，浏览器打开 http://127.0.0.1:8000，确认页面有深色样式。

- [ ] **Step 3: Commit**

```bash
git add web/styles.css
git commit -m "feat(web): add dark theme styles for 5 views + cheat panel"
```

---

### Task C7: web/app.js — state object + view switcher

**Files:**
- Create: `web/app.js`

- [ ] **Step 1: 写 web/app.js 骨架**

```javascript
"use strict";

const state = {
  history: [],          // onboarding 对话历史 [{role, content}]
  user_model: null,
  packet: null,
  project_summary: null,
  session_id: null,
  current_state: null,
  current_question: null,
  current_focus_slots: [],
  current_os: null,
  turns: [],
  report: null,
};

function $(sel) { return document.querySelector(sel); }
function show(id) { $(id).classList.remove("hidden"); }
function hide(id) { $(id).classList.add("hidden"); }

function switchView(name) {
  ["home", "onboarding", "material", "interview", "report"].forEach(v => {
    document.querySelector("#view-" + v).classList.add("hidden");
  });
  document.querySelector("#view-" + name).classList.remove("hidden");
  window.scrollTo(0, 0);
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = await resp.text();
    try { detail = JSON.parse(detail).detail || detail; } catch (_) {}
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

// HOME → ONBOARDING
$("#btn-start").addEventListener("click", () => {
  state.history = [];
  $("#onboarding-history").innerHTML = "";
  switchView("onboarding");
  appendChat("coach", "你好。我是训练组长 Coach。请告诉我：你这次主要是为了准备保研复试还是 AI 岗位面试？项目大致是什么方向？");
});

// HOME → MATERIAL (demo path)
$("#btn-demo").addEventListener("click", () => {
  state.user_model = {
    id: "demo-user", goal: "求职 AI 算法实习", target: "求职",
    target_program: "字节跳动 AI Lab 实习",
    preferred_style: "直接", current_stage: "普通项目面",
    projects: [], strengths: [], recurring_weaknesses: [], resume_issues: [],
  };
  $("#material-input").value = DEMO_PROJECT_TEXT;
  switchView("material");
});

const DEMO_PROJECT_TEXT = `我做了一个面向中小企业财务部门的 AI 财务助理，可以解析 Excel 报表、PDF 合同、发票图片等多源凭证，自动完成数据清洗和报表生成。系统采用"AI 生成公式，本地引擎核算"的架构，AI 只基于表结构生成计算规则，不接触真实数值，以降低数据泄露风险。`;

// REPORT → HOME
$("#btn-home").addEventListener("click", () => switchView("home"));
```

- [ ] **Step 2: Smoke 浏览器交互**

启动 serve，打开页面，点击「开始训练」应进入 ONBOARDING；点击「使用示例项目体验」应跳到 MATERIAL 且 textarea 预填充.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): add state object + view switcher + home→onboarding/demo entry"
```

---

### Task C8: web/app.js — Onboarding 流程接入 /api/coach/onboard

**Files:**
- Modify: `web/app.js`

- [ ] **Step 1: 在 web/app.js 末尾追加**

```javascript
function appendChat(who, text) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.innerHTML = `<span class="who">${who === "coach" ? "Coach:" : "你:"}</span>${text}`;
  $("#onboarding-history").appendChild(div);
  $("#onboarding-history").scrollTop = $("#onboarding-history").scrollHeight;
}

$("#btn-onboarding-send").addEventListener("click", async () => {
  const input = $("#onboarding-input");
  const msg = input.value.trim();
  if (!msg) return;
  appendChat("user", msg);
  input.value = "";
  state.history.push({ role: "user", content: msg });
  $("#btn-onboarding-send").disabled = true;
  try {
    const result = await postJson("/api/coach/onboard", {
      user_message: msg,
      history: state.history.slice(0, -1),  // 去掉刚 push 的本轮
    });
    if (result.need_more_info) {
      const reply = (result.followup_questions || ["请再多说一些。"]).join("\n");
      appendChat("coach", reply);
      state.history.push({ role: "assistant", content: reply });
    } else {
      state.user_model = result.user_model;
      appendChat("coach", `好。target=${result.user_model.target}，我已经记下你的目标。下一步请粘贴你的项目经历。`);
      setTimeout(() => switchView("material"), 1200);
    }
  } catch (e) {
    appendChat("coach", "出错了：" + e.message);
  } finally {
    $("#btn-onboarding-send").disabled = false;
  }
});
```

- [ ] **Step 2: Smoke**

启动 serve，HOME→开始训练→输入「我准备保研人工智能创新中心，项目是 AI 财会助理」→ 应在数秒内得到 Coach 回复（要么继续问、要么进入 MATERIAL）.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): wire onboarding to /api/coach/onboard with chat history"
```

---

### Task C9: web/app.js — Material → parse + plan + start

**Files:**
- Modify: `web/app.js`

- [ ] **Step 1: 在 web/app.js 末尾追加**

```javascript
$("#btn-material-start").addEventListener("click", async () => {
  const text = $("#material-input").value.trim();
  if (text.length < 50) {
    alert("请粘贴至少 50 字符的项目经历");
    return;
  }
  $("#btn-material-start").disabled = true;
  $("#btn-material-start").textContent = "Coach 正在备课...";
  try {
    const parsed = await postJson("/api/profile/parse", { raw_project_text: text });
    state.project_summary = parsed.project_summary;

    const plan = await postJson("/api/coach/plan", {
      user_model: state.user_model,
      project_summary: parsed.project_summary,
    });
    state.packet = plan.interview_packet;

    const start = await postJson("/api/interviewer/start", {
      interview_packet: state.packet,
      user_model: state.user_model,
    });
    state.session_id = start.session_id;
    state.current_state = start.state;
    state.current_question = start.question;
    state.current_focus_slots = start.focus_slots;
    state.current_os = start.interviewer_os;

    renderInterviewView();
    switchView("interview");
  } catch (e) {
    alert("出错：" + e.message);
  } finally {
    $("#btn-material-start").disabled = false;
    $("#btn-material-start").textContent = "开始面试";
  }
});

function renderInterviewView() {
  $("#interview-stage").textContent = "当前阶段: " + (state.current_state || "");
  $("#interview-focus").textContent = "重点: " + (state.current_focus_slots || []).join(" / ");
  $("#interview-question").textContent = state.current_question || "";
  $("#interview-input").value = "";
  hide("#interview-feedback");
  if (state.current_os) {
    show("#btn-cheat-toggle");
    renderCheatPanel(state.current_os);
  }
  hide("#cheat-panel");
}
```

- [ ] **Step 2: Smoke**

启动 serve，跑完 onboard → 在 material 页粘贴足够长文本（用 demo 按钮预填充也行）→ 点 「开始面试」→ 应跳到 INTERVIEW 显示第一问.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): wire material→parse→plan→interview start chain"
```

---

### Task C10: web/app.js — Interview 多轮 + 作弊模式 + Report

**Files:**
- Modify: `web/app.js`

- [ ] **Step 1: 在 web/app.js 末尾追加**

```javascript
$("#btn-interview-submit").addEventListener("click", async () => {
  const ans = $("#interview-input").value.trim();
  if (!ans) return;
  $("#btn-interview-submit").disabled = true;
  try {
    const result = await postJson("/api/interviewer/next", {
      session_id: state.session_id,
      answer: ans,
    });
    state.turns.push(result.turn);
    state.current_state = result.next_state;
    state.current_question = result.turn.next_question;
    state.current_os = result.turn.interviewer_os;
    renderInterviewView();
    showFeedback(result.turn);
    if (!result.should_continue) {
      hide("#btn-interview-submit");
      show("#btn-finish");
    }
  } catch (e) {
    alert("出错：" + e.message);
  } finally {
    $("#btn-interview-submit").disabled = false;
  }
});

function showFeedback(turn) {
  const div = $("#interview-feedback");
  const miss = (turn.missing_slots || []).map(s => `<span class="miss">${s}</span>`).join("、");
  div.innerHTML = `
    <div><b>反馈:</b> ${escapeHtml(turn.feedback || "（无反馈）")}</div>
    ${miss ? `<div style="margin-top:8px"><b>缺失槽位:</b> ${miss}</div>` : ""}
    <div style="margin-top:8px;color:#8b949e;font-size:12px">score: ${turn.score} / 100</div>
  `;
  show("#interview-feedback");
}

$("#btn-cheat-toggle").addEventListener("click", () => {
  const panel = $("#cheat-panel");
  panel.classList.toggle("hidden");
});

function renderCheatPanel(os) {
  const panel = $("#cheat-panel");
  panel.className = "cheat-panel hidden risk-" + ({
    "低": "low", "中": "mid", "高": "high",
  }[os.risk_level] || "mid");
  panel.innerHTML = `
    <h3>面试官内心 OS &nbsp; <small style="opacity:0.7">风险: ${os.risk_level}</small></h3>
    <p><b>真正担心:</b> ${escapeHtml(os.hidden_concern)}</p>
    <p><b>为什么追问:</b> ${escapeHtml(os.why_this_question)}</p>
    <p><b>缺失槽位:</b></p>
    <ul>${(os.missing_slots || []).map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
    <p><b>想听到:</b></p>
    <ul>${(os.what_i_want_to_hear || []).map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
  `;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

$("#btn-finish").addEventListener("click", async () => {
  $("#btn-finish").disabled = true;
  $("#btn-finish").textContent = "Coach 正在写报告...";
  try {
    const report = await postJson("/api/coach/review", { session_id: state.session_id });
    state.report = report;
    renderReport(report);
    switchView("report");
  } catch (e) {
    alert("出错：" + e.message);
  } finally {
    $("#btn-finish").disabled = false;
    $("#btn-finish").textContent = "结束面试 → 看报告";
  }
});

function renderReport(r) {
  $("#report-content").innerHTML = `
    <section>
      <h3>总分</h3>
      <div class="score">${r.overall_score} <small style="font-size:18px;opacity:0.5">/ 100</small></div>
      <p>${escapeHtml(r.summary)}</p>
    </section>
    <section>
      <h3>关键证据</h3>
      ${r.evidence.map(e => `
        <div style="margin:12px 0;padding:8px;background:#0d1117;border-radius:6px">
          <div>你说: <i>"${escapeHtml(e.quote)}"</i></div>
          <div style="margin-top:6px;color:#f85149">问题: ${escapeHtml(e.problem)}</div>
          <div style="margin-top:6px;color:#3fb950">建议: ${escapeHtml(e.suggestion)}</div>
        </div>`).join("")}
    </section>
    <section>
      <h3>最危险的追问</h3>
      <ol>${r.dangerous_questions.map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ol>
    </section>
    <section class="resume-rewrite">
      <h3>简历改写</h3>
      <div class="original">原文: ${escapeHtml(r.resume_rewrite.original)}</div>
      <div class="rewritten">改写: ${escapeHtml(r.resume_rewrite.rewritten)}</div>
      ${r.resume_rewrite.missing_evidence.length ? `<div style="margin-top:8px;color:#d29922">仍缺: ${r.resume_rewrite.missing_evidence.map(escapeHtml).join("、")}</div>` : ""}
    </section>
    <section>
      <h3>下一轮训练计划 — 推荐 ${escapeHtml(r.next_training_plan.recommended_next_step)}</h3>
      <p>${escapeHtml(r.next_training_plan.reason)}</p>
      <ul>${r.next_training_plan.steps.map(s => `<li><b>${escapeHtml(s.name)}</b>: ${escapeHtml(s.goal)} — <small>${escapeHtml(s.why_now)}</small></li>`).join("")}</ul>
    </section>
    <section class="humor">
      <h3>${escapeHtml(r.humor_card.title)}</h3>
      <pre style="white-space:pre-wrap;font-family:inherit;margin:0">${escapeHtml(r.humor_card.content)}</pre>
    </section>
  `;
}

$("#btn-replay").addEventListener("click", () => {
  // 一键重练：重置 session 但保留 user_model，回到 material
  state.session_id = null;
  state.turns = [];
  state.report = null;
  switchView("material");
});
```

- [ ] **Step 2: e2e Smoke**

启动 serve，跑 demo 路径：HOME → 使用示例项目 → 开始面试 → 答 1-2 轮 → 点结束 → 看报告.

每个 turn 后展开作弊模式确认显示正常.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): add interview multi-turn + cheat panel + report rendering + replay"
```

---

### Task C11: Demo 路径打磨 + e2e 回放

**Files:**
- 视情况修小 bug

- [ ] **Step 1: 完整跑一次 demo 路径，记录卡顿点**

打开浏览器访问本地 serve，按以下顺序操作：

1. HOME → 「使用示例项目体验」
2. MATERIAL（已预填财会 Agent）→ 「开始面试」
3. INTERVIEW 第 1 问出现
4. **故意答空泛**：输入「这个项目挺有意义的」→ 提交
5. 验证 feedback 显示 missing_slots
6. 展开作弊模式，确认 5 个字段都有内容
7. 答 2-3 轮真实回答 → 验证 state 推进
8. 点结束 → 验证报告页 5 个 section 都有内容（总分 / 证据 / 危险追问 / 简历改写 / 训练计划 / 幽默卡片）
9. 点「一键重练」→ 应回到 MATERIAL

- [ ] **Step 2: 修任何卡顿 / 显示 bug**

常见问题与排查：
- LLM 慢（>10s）→ 在按钮加 spinner
- JSON parse 失败导致前端崩溃 → 加 try/catch + 友好错误提示
- 作弊模式字段缺失 → 检查 LLM 输出是否完整 InterviewerOS

- [ ] **Step 3: 性能验证**

```bash
# 重复 3 次完整 demo，记录每次总耗时
time (curl -s -X POST http://127.0.0.1:8000/api/coach/onboard -H 'Content-Type: application/json' -d '{"user_message":"我做 AI 财会"}' > /dev/null)
```

Expected: 单 onboard ~3-5s（DeepSeek 延迟）.

- [ ] **Step 4: Commit (如有修复)**

```bash
git add -A
git commit -m "fix(web): demo path polish — error handling + spinners + edge cases"
```

---

### Task C12: 部署到 aiic.fomalhaut647.com

**Files:**
- 服务器侧操作

- [ ] **Step 1: SSH 到服务器**

```bash
ssh ubuntu@43.156.109.192
```

- [ ] **Step 2: pull 最新代码 + 装依赖**

```bash
cd /home/ubuntu/AIIC-Project   # 或 v1 部署目录；如不同则确认
git pull
pixi install
```

- [ ] **Step 3: 同步 .env（含 DEEPSEEK_API_KEY）**

如本地 `.env` 与服务器不同步，scp 或手动编辑：

```bash
nano .env  # 确保 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL 都在
```

- [ ] **Step 4: 重启 systemd 服务**

```bash
sudo systemctl restart aiic-chat
sudo systemctl status aiic-chat | head -10
```

Expected: `active (running)`.

- [ ] **Step 5: 验证健康 + 真实 endpoint**

```bash
curl -s -u aiic:'<密码>' https://aiic.fomalhaut647.com/api/healthz | python3 -m json.tool
```

Expected: `status: ok`, `commit_hash` 与本地最新 commit 一致.

- [ ] **Step 6: 浏览器验证 Demo 路径**

在本地浏览器打开 https://aiic.fomalhaut647.com，输入 Basic Auth，确认 demo 走得通.

- [ ] **Step 7: 验证主办方 SSH key 仍生效**

```bash
sudo grep -c "lbh@MacBookPro\|di@Dis-MacBook-Air" /home/ubuntu/.ssh/authorized_keys
```

Expected: `2`.

- [ ] **Step 8: 记录部署 commit**

在本地 commit message 或 progress 文件记录此次部署的 commit hash + 时间.

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — deployed commit $(git rev-parse --short HEAD)" >> docs/progress/deployments.log
git add docs/progress/deployments.log
git commit -m "deploy: live at aiic.fomalhaut647.com (Plan1C complete)"
```

---

## Self-review

**Spec coverage**：
- §1 模块边界 ✓ C1 (server/) + C5 (web/)
- §2 8 endpoint ✓ C1 (healthz) + C2 (onboard/parse/plan) + C3 (start/next) + C4 (review)
- §3 SSE ✗ P1 不在本 plan 范围（已在 spec 标注）
- §4 FastAPI 项目结构 ✓ C1
- §5 前端 state machine ✓ C7
- §6 5 视图 ✓ C5 + C7-C10
- §7 作弊模式 UI ✓ C10
- §8 Demo 路径优化 ✓ C7 (demo 按钮 hardcode user_model + project text) + C11 (回放打磨)
- §9 部署 ✓ C12

**Placeholder scan**：无 TBD / TODO；命令与代码完整；唯一 placeholder 是 C12 Step 5 的 `<密码>`（运行时由人填）.

**Type consistency**：
- request body 类（`_OnboardReq` / `_StartReq` 等）字段名与 spec C §2 一致
- 响应模型直接复用 services/schemas.py 的 Pydantic 类（OnboardResult / CoachPlanResult / EvaluationReport / InterviewTurn）→ 与 Plan1A 共享
- `services/store.py:SessionNotFound` 在 C3/C4 都正确捕获并转 404

**实施依赖外部**：
- Plan1A Tasks A6/A7/A8/A10/A11 完成后才能跑 e2e；C2-C4 在 Plan1A 实施途中可先写代码（services 模块名稳定）
- Plan1B Task B6 完成后 QuestionBank 才能从 reviewed=true 题中选题；之前 fallback 到 LLM 现场生成（已在 Spec A §5.3 设计兜底）
