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

from services import coach
from services.llm import call_deepseek
from services.prompts import PROFILE_PARSE_SYSTEM
from services.schemas import (
    CoachPlanResult,
    InterviewPacket,
    OnboardResult,
    UserModel,
)


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
    # Lazy imports — Plan1A (services.store) may not be merged yet when
    # Plan1C lands first. healthz / static serving must work without them.
    try:
        from services.store import SessionStore  # noqa: WPS433

        app.state.store = SessionStore()
    except ImportError:
        app.state.store = None

    try:
        from services.question_bank import QuestionBank  # noqa: WPS433

        app.state.bank = QuestionBank()
    except ImportError:
        app.state.bank = None

    app.state.commit_hash = _git_short_hash()
    cn_tz = timezone(timedelta(hours=8))
    app.state.deploy_time = datetime.now(cn_tz).isoformat(timespec="seconds")
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
