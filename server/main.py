"""ProjectProbe v2 — FastAPI 入口。

Spec: docs/specs/C-api-and-frontend.md §4.

Lifespan responsibilities:
- cache `commit_hash` (git short SHA) and `deploy_time` (Asia/Shanghai ISO 8601)
- best-effort attach `app.state.store` (SessionStore) and `app.state.bank`
  (QuestionBank). Both are lazy-imported because impl-A's services.store
  and impl-B's full QuestionBank may not yet be merged into main when this
  module first lands; the healthz endpoint must still respond 200 so the
  主办方 SSH check passes.
"""
from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import coach, interviewer
from services.llm import call_deepseek
from services.prompts import PROFILE_PARSE_SYSTEM
from services.schemas import (
    CoachPlanResult,
    EvaluationReport,
    InterviewPacket,
    InterviewStage,
    InterviewTurn,
    OnboardResult,
    UserModel,
)
from services.store import SessionNotFound


def _git_short_hash() -> str:
    """Short SHA of HEAD; 'unknown' if git unavailable (e.g. running from tarball)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set healthz fields FIRST so the deploy probe stays green even if a
    # downstream service constructor throws (e.g. SessionStore() does
    # mkdir(parents=True, exist_ok=True) at services/store.py:18 which can
    # raise PermissionError/OSError under restricted FS — nginx-spawned
    # uvicorn, read-only mounts, etc).  The whole point of the lazy-import
    # pattern is "healthz must respond" — must not be defeated by a
    # narrowly-scoped except clause.
    app.state.commit_hash = _git_short_hash()
    cn_tz = timezone(timedelta(hours=8))
    app.state.deploy_time = datetime.now(cn_tz).isoformat(timespec="seconds")

    # Lazy imports — Plan1A (services.store) may not be merged yet when
    # Plan1C lands first. Broad except so init failures (mkdir denied,
    # bank file missing, etc) degrade to a 503 on dependent endpoints
    # rather than a 500 on healthz.
    try:
        from services.store import SessionStore  # noqa: WPS433

        app.state.store = SessionStore()
    except Exception:
        app.state.store = None

    try:
        from services.question_bank import QuestionBank  # noqa: WPS433

        app.state.bank = QuestionBank()
    except Exception:
        app.state.bank = None

    yield
    # no cleanup needed (in-memory store)


app = FastAPI(lifespan=lifespan, title="ProjectProbe v2")


# Static frontend (web/ ↔ /static/*); index.html served at /.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def root():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "ProjectProbe v2 — frontend not built yet"}


@app.get("/api/healthz")
async def healthz():
    """Deploy probe. Hit by 主办方 after SSH login. Spec C §2.1."""
    return {
        "status": "ok",
        "version": "v2-mvp",
        "commit_hash": app.state.commit_hash,
        "deploy_time": app.state.deploy_time,
        "provider": "deepseek",
    }


# ============================================================
# Coach endpoints — Spec C §2.2 / §2.3 / §2.4
# ============================================================


class _OnboardReq(BaseModel):
    user_message: str
    history: list[dict] = []


@app.post("/api/coach/onboard", response_model=OnboardResult)
async def api_coach_onboard(body: _OnboardReq) -> OnboardResult:
    if not body.user_message.strip():
        raise HTTPException(status_code=400, detail="user_message is empty")
    return await coach.onboard(body.user_message, body.history)


class _ParseReq(BaseModel):
    raw_project_text: str


class _ParseResp(BaseModel):
    project_summary: str
    technical_keywords: list[str]
    possible_weaknesses: list[str]
    likely_followup_directions: list[str]


@app.post("/api/profile/parse", response_model=_ParseResp)
async def api_profile_parse(body: _ParseReq) -> _ParseResp:
    text = body.raw_project_text.strip()
    if len(text) < 50:
        raise HTTPException(
            status_code=400,
            detail="raw_project_text too short (need ≥ 50 chars)",
        )
    fallback = _ParseResp(
        project_summary=text[:200],
        technical_keywords=[],
        possible_weaknesses=["项目原文过短或结构不清，无法自动抽取"],
        likely_followup_directions=[],
    )
    result = await call_deepseek(
        [
            {"role": "system", "content": PROFILE_PARSE_SYSTEM},
            {"role": "user", "content": text},
        ],
        response_schema=_ParseResp,
        temperature=0.3,
        fallback=fallback,
    )
    # call_deepseek returns T (the schema instance) when response_schema given.
    return result if isinstance(result, _ParseResp) else fallback


class _PlanReq(BaseModel):
    user_model: UserModel
    project_summary: str


@app.post("/api/coach/plan", response_model=CoachPlanResult)
async def api_coach_plan(body: _PlanReq) -> CoachPlanResult:
    return await coach.plan(body.user_model, body.project_summary)


# ============================================================
# Interviewer endpoints — Spec C §2.5 / §2.6
# ============================================================


class _StartReq(BaseModel):
    interview_packet: InterviewPacket
    user_model: UserModel


class _StartResp(BaseModel):
    session_id: str
    state: InterviewStage
    question: str
    interviewer_os: dict  # InterviewerOS as plain dict (frontend convenience)
    focus_slots: list[str]


@app.post("/api/interviewer/start", response_model=_StartResp)
async def api_interviewer_start(body: _StartReq) -> _StartResp:
    if app.state.bank is None or app.state.store is None:
        raise HTTPException(
            status_code=503,
            detail="services.store / question_bank not initialised",
        )
    sid, turn = await interviewer.start(
        body.interview_packet,
        body.user_model,
        app.state.bank,
        app.state.store,
    )
    return _StartResp(
        session_id=sid,
        state=turn.state,
        question=turn.question,
        interviewer_os=turn.interviewer_os.model_dump(mode="json"),
        focus_slots=body.interview_packet.focus_slots,
    )


class _NextReq(BaseModel):
    session_id: str
    answer: str


class _NextResp(BaseModel):
    turn: InterviewTurn
    should_continue: bool
    next_state: InterviewStage


@app.post("/api/interviewer/next", response_model=_NextResp)
async def api_interviewer_next(body: _NextReq) -> _NextResp:
    if app.state.bank is None or app.state.store is None:
        raise HTTPException(status_code=503, detail="services not ready")
    if not body.answer.strip():
        raise HTTPException(status_code=400, detail="answer is empty")
    try:
        turn, cont, st = await interviewer.next_turn(
            body.session_id,
            body.answer,
            app.state.bank,
            app.state.store,
        )
    except SessionNotFound:
        raise HTTPException(
            status_code=404,
            detail={"error": "session_expired", "message": "请重新开始训练"},
        )
    return _NextResp(turn=turn, should_continue=cont, next_state=st)


# ============================================================
# Coach review — Spec C §2.7
# ============================================================


class _ReviewReq(BaseModel):
    session_id: str


@app.post("/api/coach/review", response_model=EvaluationReport)
async def api_coach_review(body: _ReviewReq) -> EvaluationReport:
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="store not initialised")
    try:
        session = app.state.store.get(body.session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.turns:
        raise HTTPException(
            status_code=400,
            detail="no turns to review — session has 0 answered questions",
        )
    return await coach.review(
        session.user_model, session.packet, session.turns,
    )
