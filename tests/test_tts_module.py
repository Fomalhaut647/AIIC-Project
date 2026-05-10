"""TTS module tests — Spec E §9.1."""
from unittest.mock import patch

import httpx
import pytest

from services.tts import synthesize_speech


@pytest.mark.asyncio
async def test_synthesize_speech_happy(monkeypatch):
    """正常调用返 bytes。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake_resp = httpx.Response(
        status_code=200,
        content=b"\x00\x01\x02 fake mp3 bytes",
        request=httpx.Request("POST", "https://x/v1/audio/speech"),
    )

    async def fake_post(*args, **kwargs):
        return fake_resp

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        audio = await synthesize_speech("你好世界")

    assert audio.startswith(b"\x00\x01\x02")


@pytest.mark.asyncio
async def test_synthesize_speech_retry_once(monkeypatch):
    """第一次 NetworkError → retry → 第二次成功。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    call_count = {"n": 0}
    fake_ok = httpx.Response(
        status_code=200,
        content=b"recovered audio",
        request=httpx.Request("POST", "https://x/v1/audio/speech"),
    )

    async def flaky_post(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.NetworkError("transient")
        return fake_ok

    with patch("httpx.AsyncClient.post", side_effect=flaky_post):
        audio = await synthesize_speech("hi")

    assert audio == b"recovered audio"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_synthesize_speech_persistent_failure_raises(monkeypatch):
    """两次都 NetworkError → 抛。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    async def always_fail(*args, **kwargs):
        raise httpx.NetworkError("down")

    with patch("httpx.AsyncClient.post", side_effect=always_fail):
        with pytest.raises(httpx.NetworkError):
            await synthesize_speech("hi")


@pytest.mark.asyncio
async def test_synthesize_speech_4xx_raises(monkeypatch):
    """API 返 4xx → raise_for_status 抛 HTTPStatusError，不 retry。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake_400 = httpx.Response(
        status_code=400,
        text="bad request",
        request=httpx.Request("POST", "https://x/v1/audio/speech"),
    )

    async def fake_post(*args, **kwargs):
        return fake_400

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        with pytest.raises(httpx.HTTPStatusError):
            await synthesize_speech("hi")


@pytest.mark.asyncio
async def test_synthesize_speech_missing_api_key(monkeypatch):
    """缺 MIMO_API_KEY → KeyError（fail-fast）。"""
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    with pytest.raises(KeyError):
        await synthesize_speech("hi")
