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

import os
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import coach, interviewer
from services.export import render_markdown
# Plan2 P7: re-export coach.{onboard,plan,review} as module-level names so
# tests can `patch("server.main.coach_onboard", fake)`. The bare-`coach`
# import is retained for backward compatibility with code paths that still
# reference `coach.X` directly.
from services.coach import (
    onboard as coach_onboard,
    plan as coach_plan,
    review as coach_review,
)
from services.llm import call_deepseek
from services.prompts import PROFILE_PARSE_SYSTEM
from services.schemas import (
    CoachPlanResult,
    EvaluationReport,
    InterviewerOS,
    InterviewPacket,
    InterviewStage,
    InterviewTurn,
    OnboardResult,
    QuestionSource,
    RiskLevel,
    SessionMeta,
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

        # Plan2 P7: read DATA_DIR fresh each lifespan startup so tests can
        # `monkeypatch.setenv("DATA_DIR", str(tmp_path))` and pick up an
        # isolated data root via `with TestClient(app) as c:`. Caching this
        # at import time would defeat the monkeypatch.
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        app.state.store = SessionStore(data_dir=data_dir)
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
    user_id: str = "anonymous"  # Plan2 P7: 长期训练用户标识 (Spec D §6.2)


@app.post("/api/coach/onboard", response_model=OnboardResult)
async def api_coach_onboard(body: _OnboardReq) -> OnboardResult:
    if not body.user_message.strip():
        raise HTTPException(status_code=400, detail="user_message is empty")
    return await coach_onboard(body.user_message, body.history)


class _ParseReq(BaseModel):
    raw_project_text: str
    user_id: str = "anonymous"  # Plan2 P7


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
    user_id: str = "anonymous"  # Plan2 P7


@app.post("/api/coach/plan", response_model=CoachPlanResult)
async def api_coach_plan(body: _PlanReq) -> CoachPlanResult:
    return await coach_plan(body.user_model, body.project_summary)


# ============================================================
# Interviewer endpoints — Spec C §2.5 / §2.6
# ============================================================


class _StartReq(BaseModel):
    interview_packet: InterviewPacket
    user_model: UserModel
    user_id: str = "anonymous"  # Plan2 P7


class _StartResp(BaseModel):
    session_id: str
    state: InterviewStage
    question: str
    interviewer_os: dict  # InterviewerOS as plain dict (frontend convenience)
    focus_slots: list[str]


# Demo mode (Spec C §8.2): hardcoded high-quality S1 question that bypasses
# the LLM for the demo video's first 30 seconds. Subsequent /next calls still
# hit real LLM, so the wow moment (vague answer → missing_slots) is preserved.
# Tuned for the LedgerCraft (财会 Agent) sample project loaded by the HOME
# 「使用示例项目」button.
_DEMO_FOCUS_SLOTS = ["pain_real", "target_user"]


def _build_demo_first_turn(session_id: str) -> InterviewTurn:
    return InterviewTurn(
        id=uuid.uuid4().hex,
        session_id=session_id,
        state=InterviewStage.S1_MOTIVATION,
        question=(
            "你是怎么发现这个财务痛点真实存在的？"
            "你访谈过几个真实用户吗？"
        ),
        answer="",
        score=0,
        covered_slots=[],
        missing_slots=[],
        feedback="",
        next_question="",
        source=QuestionSource.PROJECT,
        interviewer_os=InterviewerOS(
            hidden_concern=(
                "候选人可能只在描述系统功能，并没有验证过财务部门"
                "真实痛点；如果连一个用户访谈都拿不出来，后续技术细节"
                "都站不住。"
            ),
            why_this_question=(
                "痛点的真实性是这个项目能否被实验室 / 公司接受的根基。"
                "第一问就问这个，能立刻分辨出 '做了 demo' 和 "
                "'解决了真实问题' 两类候选人。"
            ),
            missing_slots=["pain_real", "target_user"],
            what_i_want_to_hear=[
                "具体的访谈对象（多少人 / 角色 / 行业）",
                "他们抱怨的原话或具体场景",
                "现有解决方案为什么不够",
            ],
            risk_level=RiskLevel.MEDIUM,
        ),
    )


@app.post("/api/interviewer/start", response_model=_StartResp)
async def api_interviewer_start(
    body: _StartReq,
    demo: bool = Query(
        False,
        description=(
            "Spec C §8.2: bypass LLM and return a hardcoded S1 question + OS "
            "for demo video reliability. Subsequent /next calls still use LLM."
        ),
    ),
) -> _StartResp:
    if app.state.bank is None or app.state.store is None:
        raise HTTPException(
            status_code=503,
            detail="services.store / question_bank not initialised",
        )
    if demo:
        sid = app.state.store.create(body.interview_packet, body.user_model)
        turn = _build_demo_first_turn(sid)
        # Persist so subsequent /interviewer/next finds the session + can
        # reference this as last_turn.
        app.state.store.append_turn(sid, turn)
        return _StartResp(
            session_id=sid,
            state=turn.state,
            question=turn.question,
            interviewer_os=turn.interviewer_os.model_dump(mode="json"),
            # Override packet focus_slots with demo-specific (pain_real /
            # target_user) so the banner aligns with the hardcoded question.
            focus_slots=_DEMO_FOCUS_SLOTS,
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
    user_id: str = "anonymous"  # Plan2 P7


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
    user_id: str = "anonymous"  # Plan2 P7


@app.post("/api/coach/review", response_model=EvaluationReport)
async def api_coach_review(body: _ReviewReq) -> EvaluationReport:
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="store not initialised")
    try:
        session = app.state.store.get(body.session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found")
    # Spec C §2.7: 400 when (state != DONE AND turns < 6). Either condition
    # alone passing means the session is "complete enough" for a meaningful
    # report. Both failing means the user hit the finish button prematurely.
    if (
        session.state != InterviewStage.DONE
        and len(session.turns) < 6
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"session not yet finished (state={session.state.value}, "
                f"turns={len(session.turns)}); need state=done or turns>=6"
            ),
        )
    report = await coach_review(
        session.user_model, session.packet, session.turns,
    )

    # Plan2 P8: persist report on session JSON dump so export.md can find it
    # later (Spec D §9.1 implicit "reviewed" status = report present).
    session.evaluation_report = report
    app.state.store._dump(session)

    # Plan2 P7: aggregate SessionMeta into user profile (Spec D §6.2 review hook).
    # Best-effort: if profile write fails, the user still gets the report
    # back (this is a side-channel; not a blocker for the primary response).
    try:
        meta = SessionMeta(
            session_id=body.session_id,
            # session creation timestamp not tracked in v2 InterviewSession;
            # use now() as a close approximation (review fires at end of session).
            # TODO: thread real created_at through services/store.py SessionStore.create()
            # so dashboard timeline shows session start, not review time.
            created_at=datetime.now(),
            target=session.packet.target,
            project_summary_short=session.packet.project_summary[:80],
            overall_score=report.overall_score,
            weakness_tags=report.weaknesses,
            parent_session_id=session.packet.parent_session_id,
            is_replay=session.packet.replay_mode,
        )
        await app.state.store.update_user_profile(body.user_id, meta)
    except Exception as e:
        # Profile aggregation is non-critical; surface report regardless.
        # Log to stderr so production failures leave a trail (no logger configured;
        # consistent with existing module's print/print-fallback style).
        import sys
        print(
            f"[plan2] user_profile update failed for user_id={body.user_id!r} "
            f"session_id={body.session_id!r}: {e!r}",
            file=sys.stderr,
        )

    return report


# ============================================================
# Plan2 P8: profile + markdown export — Spec D §6.1 / §9
# ============================================================


@app.get("/api/users/{user_id}/profile")
async def get_user_profile(user_id: str):
    """Spec D §6.1 — UserProfile aggregator. Missing user → empty profile
    (200 + default UserProfile, NOT 404). The dashboard always lands on
    something renderable even for first-time visitors."""
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="store not initialised")
    profile = app.state.store.load_user_profile(user_id)
    return profile.model_dump(mode="json")


@app.get("/api/sessions/{session_id}/export.md")
async def export_session_markdown(session_id: str):
    """Spec D §6.1 + §9 — 8-section markdown export.

    - 404: session JSON dump not on disk
    - 409: session exists but evaluation_report missing (call /coach/review first)
    - 200: text/markdown attachment with full 8-section report
    """
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="store not initialised")
    session_dict = app.state.store.load_session_dict(session_id)
    if session_dict is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not session_dict.get("evaluation_report"):
        raise HTTPException(
            status_code=409,
            detail="session has not been reviewed yet; call /api/coach/review first",
        )

    md = render_markdown(session_dict)
    score = session_dict["evaluation_report"].get("overall_score", 0)
    short = session_id[:8]
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"projectprobe-{short}-{date}-score{score}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
