"""Plan2 profile + export endpoints tests — Spec D §6.1 / §9.1."""
import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def _evaluation_report() -> dict:
    """A valid EvaluationReport JSON dict for tests (matches v2 schema)."""
    return {
        "overall_score": 70,
        "summary": "OK",
        "strengths": [],
        "weaknesses": [],
        "evidence": [{"quote": "q", "problem": "p", "suggestion": "s"}],
        "dangerous_questions": ["d1", "d2"],
        "resume_rewrite": {
            "original": "", "rewritten": "", "missing_evidence": [],
            "revision_history": [],
        },
        "next_training_plan": {
            "recommended_next_step": "普通项目面",
            "reason": "ok",
            "steps": [
                {"name": "a", "goal": "g", "why_now": "w"},
                {"name": "b", "goal": "g", "why_now": "w"},
            ],
        },
        "humor_card": {"title": "T", "content": "C"},
    }


def _seed_session_with_report(client, session_id_marker: str = "sess-done") -> str:
    """Create a real session via store.create, attach a report, dump to disk."""
    from services.schemas import InterviewPacket, UserModel, Target, EvaluationReport
    store = client.app.state.store
    pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="测试项目 P 中文", focus_slots=["baseline"],
    )
    um = UserModel(id="u1", goal="保研", target=Target.BAOYAN)
    sid = store.create(pkt, um)
    session = store.get(sid)
    session.evaluation_report = EvaluationReport.model_validate(_evaluation_report())
    store.persist(session)  # persist with report (public alias of _dump)
    return sid


def test_get_profile_empty_user_returns_default(client):
    """不存在的 user_id 返回 200 + 空 profile（不是 404, per Spec D §6.1）。"""
    r = client.get("/api/users/ghost-user/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "ghost-user"
    assert body["total_sessions"] == 0
    assert body["sessions"] == []


def test_get_profile_existing_user(client, tmp_path: Path):
    """先 seed 一个 user profile 文件，然后查询."""
    users_dir = tmp_path / "users"
    users_dir.mkdir(exist_ok=True)
    (users_dir / "u1.json").write_text(json.dumps({
        "user_id": "u1",
        "created_at": datetime(2026, 5, 12).isoformat(),
        "sessions": [
            {
                "session_id": "s1",
                "created_at": datetime(2026, 5, 12).isoformat(),
                "target": "保研",
                "project_summary_short": "财会",
                "overall_score": 80,
                "weakness_tags": ["baseline"],
                "is_replay": False,
            },
        ],
        "total_sessions": 1,
        "average_score": 80.0,
        "recurring_weaknesses": {"baseline": 1},
        "projects": ["财会"],
    }), encoding="utf-8")

    r = client.get("/api/users/u1/profile")
    assert r.status_code == 200
    assert r.json()["total_sessions"] == 1
    assert r.json()["recurring_weaknesses"] == {"baseline": 1}


def test_export_markdown_404_when_session_missing(client):
    """完全不存在的 session_id → 404."""
    r = client.get("/api/sessions/nonexistent-sid/export.md")
    assert r.status_code == 404


def test_export_markdown_409_when_review_missing(client):
    """session 存在但没有 evaluation_report → 409."""
    from services.schemas import InterviewPacket, UserModel, Target
    store = client.app.state.store
    pkt = InterviewPacket(
        target=Target.BAOYAN, interviewer_style="strict",
        project_summary="X", focus_slots=["baseline"],
    )
    um = UserModel(id="u1", goal="保研", target=Target.BAOYAN)
    sid = store.create(pkt, um)
    # Force the session JSON to disk without report (use public persist).
    store.persist(store.get(sid))

    r = client.get(f"/api/sessions/{sid}/export.md")
    assert r.status_code == 409, r.text


def test_export_markdown_returns_markdown_file(client):
    """完整 session（含 evaluation_report） → 200 + Content-Type: text/markdown."""
    sid = _seed_session_with_report(client)

    r = client.get(f"/api/sessions/{sid}/export.md")
    assert r.status_code == 200, r.text
    assert "text/markdown" in r.headers["content-type"]
    assert r.headers.get("content-disposition", "").startswith("attachment;")
    assert "ProjectProbe 复盘报告" in r.text
    assert "## 1." in r.text
    assert "## 8." in r.text


def test_export_markdown_content_type_includes_utf8_charset(client):
    """Spec D §6.1: text/markdown; charset=utf-8 — UTF-8 round-trip 中文字符."""
    sid = _seed_session_with_report(client)
    r = client.get(f"/api/sessions/{sid}/export.md")
    assert r.status_code == 200
    ct = r.headers["content-type"]
    assert "text/markdown" in ct
    assert "charset=utf-8" in ct.lower()
    # 中文 UTF-8 round-trip
    assert "测试项目" in r.text  # 来自 project_summary
    assert "训练计划" in r.text or "下一轮" in r.text  # 来自 sec 6 标题


def test_export_markdown_filename_format(client):
    """Spec D §6.1 filename: projectprobe-{8-char-prefix}-{YYYY-MM-DD}-score{N}.md"""
    import re
    sid = _seed_session_with_report(client)
    r = client.get(f"/api/sessions/{sid}/export.md")
    cd = r.headers.get("content-disposition", "")
    # 匹配 attachment; filename="projectprobe-XXXXXXXX-YYYY-MM-DD-scoreNN.md"
    m = re.search(r'filename="(projectprobe-[0-9a-f]{8}-\d{4}-\d{2}-\d{2}-score\d+\.md)"', cd)
    assert m is not None, f"Content-Disposition pattern mismatch: {cd!r}"
    fname = m.group(1)
    assert sid[:8] in fname  # 前 8 字符 = session_id 前缀
    assert "score70" in fname  # _evaluation_report() 设的 overall_score


def test_export_markdown_renders_training_plan_dict_readable(client):
    """回归: next_training_plan 是 TrainingPlan dict 不是 str；之前 f-string 直接
    把 dict 转成 Python repr 给用户看。修复后应渲染为可读 markdown。"""
    sid = _seed_session_with_report(client)
    r = client.get(f"/api/sessions/{sid}/export.md")
    assert r.status_code == 200
    # 不应是 Python dict repr
    assert "{'recommended_next_step'" not in r.text
    assert "{'name'" not in r.text
    # 应该有可读字段
    assert "推荐下一步" in r.text or "普通项目面" in r.text
    assert "原因" in r.text or "ok" in r.text
    # 步骤
    assert "**步骤**" in r.text or "1." in r.text
