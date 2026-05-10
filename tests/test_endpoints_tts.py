"""Plan3 /api/tts/synthesize endpoint tests — Spec E §9.2."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "fake")
    with TestClient(app) as c:
        yield c


def test_tts_happy(client):
    fake = AsyncMock(return_value=b"fake mp3 bytes")
    with patch("server.main.synthesize_speech", fake):
        r = client.post("/api/tts/synthesize", json={"text": "你好世界"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.content == b"fake mp3 bytes"


def test_tts_voice_passed_user_id_ignored(client):
    """voice 透传给 wrapper；user_id 仅用于 endpoint 层（配额/日志），
    Q3 wrapper 签名 (text, voice, *, timeout) 不收 user_id 是设计意图。"""
    fake = AsyncMock(return_value=b"x")
    with patch("server.main.synthesize_speech", fake) as p:
        r = client.post("/api/tts/synthesize", json={
            "text": "hi", "voice": "alto", "user_id": "u1",
        })
    assert r.status_code == 200
    p.assert_awaited_once_with("hi", "alto")  # 仅 2 个 positional args，user_id 不透传


def test_tts_empty_text_422(client):
    r = client.post("/api/tts/synthesize", json={"text": ""})
    assert r.status_code == 422


def test_tts_blank_text_422(client):
    r = client.post("/api/tts/synthesize", json={"text": "   "})
    assert r.status_code == 422


def test_tts_text_too_long_422(client):
    r = client.post("/api/tts/synthesize", json={"text": "x" * 4001})
    assert r.status_code == 422


def test_tts_upstream_failure_503(client):
    fake = AsyncMock(side_effect=httpx.NetworkError("down"))
    with patch("server.main.synthesize_speech", fake):
        r = client.post("/api/tts/synthesize", json={"text": "hi"})
    assert r.status_code == 503
    # generic upstream failure detail
    assert "upstream" in r.json()["detail"]


def test_tts_missing_api_key_503(client):
    """KeyError (MIMO_API_KEY 未配) → 503 with detail 区分 'not configured'。
    保护 except KeyError 分流不被未来重构 silent 干掉。
    注意 detail 不再含 env var 名（防泄露攻击面提示）。"""
    fake = AsyncMock(side_effect=KeyError("MIMO_API_KEY"))
    with patch("server.main.synthesize_speech", fake):
        r = client.post("/api/tts/synthesize", json={"text": "hi"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]
    assert "MIMO_API_KEY" not in r.json()["detail"]


def test_tts_programming_bug_not_swallowed(client):
    """非 httpx 异常（程序 bug / TypeError）应 propagate，不被 503 吞掉。
    保护 narrow except (httpx.HTTPError) 不被重构回退到 bare Exception。
    生产环境 fastapi 会转 500；TestClient 默认 raise_server_exceptions=True
    会把异常抛回 test，pytest.raises 即验证"未被 endpoint 吞"。"""
    fake = AsyncMock(side_effect=TypeError("synthetic bug — wrong arg type"))
    with patch("server.main.synthesize_speech", fake):
        with pytest.raises(TypeError, match="synthetic bug"):
            client.post("/api/tts/synthesize", json={"text": "hi"})
