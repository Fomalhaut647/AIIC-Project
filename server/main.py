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

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


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
