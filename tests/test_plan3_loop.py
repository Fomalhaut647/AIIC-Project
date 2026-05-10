"""Plan3 full integration smoke — Spec E §11.3.

完整链路：upload PDF → /api/uploads → 用 parsed_text 走 onboarding（mock LLM） →
直接调 /api/tts/synthesize（模拟前端 renderInterviewerQuestion 时的调用），
验证 mock 被 await 一次且第一个 positional arg 是 question text。

完整 e2e（含麦克风授权 / TTS 真返音频）走 Q9 部署后浏览器手动 e2e，本测仅
覆盖后端三个 endpoint 的串联（upload → onboard → tts）— 不真打 LLM / TTS API。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIMO_API_KEY", "fake")
    with TestClient(app) as c:
        yield c


def _make_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text(
        (50, 50),
        "我的财会 Agent 项目：AI 生成公式 + 本地引擎核算",
        fontsize=12,
    )
    buf = BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_upload_then_onboarding(client):
    """上传 PDF 拿到 parsed_text，再用它喂 /api/coach/onboard。"""
    from services.schemas import OnboardResult

    r = client.post(
        "/api/uploads",
        files={"file": ("project.pdf", _make_pdf(), "application/pdf")},
        data={"user_id": "u-int"},
    )
    assert r.status_code == 200, r.text
    parsed = r.json()["parsed_text"]
    assert "财会" in parsed or "Agent" in parsed

    fake_onboard = AsyncMock(return_value=OnboardResult(
        need_more_info=True,
        followup_questions=["你是准备保研复试还是 AI 岗位面试？"],
    ))
    with patch("server.main.coach_onboard", fake_onboard):
        r = client.post(
            "/api/coach/onboard",
            json={
                "user_message": parsed,
                "history": [],
                "user_id": "u-int",
            },
        )
    assert r.status_code == 200, r.text
    fake_onboard.assert_awaited_once()
    # 第一个 positional arg 是 user_message — 即上传 endpoint 解析出来的文本
    assert "财会" in fake_onboard.await_args.args[0] or "Agent" in fake_onboard.await_args.args[0]


def test_tts_endpoint_called_with_question_text(client):
    """直接调 /api/tts/synthesize 模拟前端在 renderInterviewerQuestion 时的调用。"""
    fake_synth = AsyncMock(return_value=b"audio bytes")
    with patch("server.main.synthesize_speech", fake_synth) as p:
        r = client.post(
            "/api/tts/synthesize",
            json={
                "text": "你这次主要是为了准备保研复试还是 AI 岗位面试？",
                "user_id": "u-int",
            },
        )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.content == b"audio bytes"
    p.assert_awaited_once()
    # 第一个 positional arg 是 text（Q3 wrapper 签名 (text, voice)）
    assert "保研" in p.await_args.args[0]
