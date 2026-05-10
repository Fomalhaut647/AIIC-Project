"""Plan3.5 /api/stt/transcribe endpoint tests。

mock services.stt.transcribe 不真调 MiMo 网关；测 endpoint 层 validation +
错误分流（400/413/422/503）+ happy path 返回 schema。
"""
from __future__ import annotations

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


def _audio_files(name: str = "rec.webm", ctype: str = "audio/webm"):
    """构造 multipart files dict；body 用任意非空 bytes（wrapper 被 mock）。"""
    return {"file": (name, b"\x1a\x45\xdf\xa3 fake webm bytes", ctype)}


# ----- happy path -----


def test_stt_happy(client):
    fake = AsyncMock(return_value="你好世界")
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post(
            "/api/stt/transcribe",
            files=_audio_files(),
            data={"user_id": "u1"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"transcript": "你好世界", "user_id": "u1"}
    # wrapper 被以 (audio_bytes, mime) 调用
    fake.assert_awaited_once()
    args = fake.await_args
    audio_arg, mime_arg = args.args[:2]
    assert isinstance(audio_arg, bytes) and len(audio_arg) > 0
    assert mime_arg.startswith("audio/webm")


def test_stt_default_user_id_is_anonymous(client):
    fake = AsyncMock(return_value="hi")
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 200
    assert r.json()["user_id"] == "anonymous"


def test_stt_empty_transcript_ok(client):
    """LLM 返空 transcript（无清晰人声/静音）→ 200 + transcript=""，不视为错误。"""
    fake = AsyncMock(return_value="")
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 200
    assert r.json()["transcript"] == ""


def test_stt_accepts_multiple_mimes(client):
    """webm/ogg/mp3/wav/m4a/mp4/flac 都应通过 mime 粗筛。"""
    fake = AsyncMock(return_value="x")
    with patch("server.main.stt_transcribe_audio", fake):
        for ctype in [
            "audio/webm",
            "audio/webm;codecs=opus",
            "audio/ogg",
            "audio/mpeg",
            "audio/wav",
            "audio/mp4",
            "audio/m4a",
            "audio/flac",
        ]:
            r = client.post(
                "/api/stt/transcribe",
                files={"file": ("a", b"x" * 100, ctype)},
            )
            assert r.status_code == 200, f"mime={ctype} got {r.status_code} {r.text}"


# ----- validation: 400 -----


def test_stt_invalid_user_id_400(client):
    r = client.post(
        "/api/stt/transcribe",
        files=_audio_files(),
        data={"user_id": "../etc/passwd"},
    )
    assert r.status_code == 400
    assert "user_id" in r.json()["detail"]


def test_stt_unsupported_mime_400(client):
    r = client.post(
        "/api/stt/transcribe",
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")},
    )
    assert r.status_code == 400
    assert "unsupported audio mime" in r.json()["detail"]


def test_stt_text_mime_rejected_400(client):
    """text/plain / application/json 不该过 mime 粗筛。"""
    r = client.post(
        "/api/stt/transcribe",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_stt_empty_body_400(client):
    """zero-byte upload → 400 audio body is empty（不让 wrapper 浪费 token）。"""
    r = client.post(
        "/api/stt/transcribe",
        files={"file": ("a.webm", b"", "audio/webm")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"]


# ----- validation: 413 oversized -----


def test_stt_oversized_413(client):
    """6MB body > 5MB cap → 413。"""
    big = b"\x00" * (6 * 1024 * 1024)
    r = client.post(
        "/api/stt/transcribe",
        files={"file": ("big.webm", big, "audio/webm")},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"]


# ----- error mapping: 422 / 503 -----


def test_stt_decode_failure_422(client):
    """ffmpeg 转码失败 (RuntimeError) → 422 audio decode failed。"""
    fake = AsyncMock(side_effect=RuntimeError("ffmpeg: invalid data"))
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 422
    assert "decode" in r.json()["detail"]
    # 不暴露 ffmpeg 内部 stderr 详情
    assert "ffmpeg" not in r.json()["detail"].lower()


def test_stt_upstream_failure_503(client):
    fake = AsyncMock(side_effect=httpx.NetworkError("down"))
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 503
    assert "upstream" in r.json()["detail"]


def test_stt_upstream_4xx_503(client):
    """MiMo 4xx → wrapper 抛 httpx.HTTPStatusError → endpoint 503。"""
    fake = AsyncMock(side_effect=httpx.HTTPStatusError(
        "bad", request=httpx.Request("POST", "https://x"),
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
    ))
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 503


def test_stt_missing_api_key_503(client):
    """KeyError → 503 with detail 'STT not configured'（对偶 TTS）。"""
    fake = AsyncMock(side_effect=KeyError("MIMO_API_KEY"))
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]
    # 不暴露 env var 名
    assert "MIMO_API_KEY" not in r.json()["detail"]


def test_stt_empty_audio_valueerror_400(client):
    """wrapper 抛 ValueError (empty audio_bytes) → 400 client error。"""
    # endpoint 自己已拦 empty body 400；这里测 wrapper 层 ValueError 也走 400 path
    fake = AsyncMock(side_effect=ValueError("audio_bytes is empty"))
    with patch("server.main.stt_transcribe_audio", fake):
        r = client.post("/api/stt/transcribe", files=_audio_files())
    assert r.status_code == 400


def test_stt_programming_bug_not_swallowed(client):
    """非 httpx/Value/Runtime/Key 异常（程序 bug）应 propagate，不被 503 吞掉。

    保护 narrow except 列表不被未来重构回退到 bare Exception。
    """
    fake = AsyncMock(side_effect=TypeError("synthetic bug"))
    with patch("server.main.stt_transcribe_audio", fake):
        with pytest.raises(TypeError, match="synthetic bug"):
            client.post("/api/stt/transcribe", files=_audio_files())
