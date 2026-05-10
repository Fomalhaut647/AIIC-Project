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


def test_tts_passes_voice_and_user_id(client):
    fake = AsyncMock(return_value=b"x")
    with patch("server.main.synthesize_speech", fake) as p:
        r = client.post("/api/tts/synthesize", json={
            "text": "hi", "voice": "alto", "user_id": "u1",
        })
    assert r.status_code == 200
    p.assert_awaited_once_with("hi", "alto")  # voice 被透传


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
