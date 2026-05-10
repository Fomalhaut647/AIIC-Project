"""STT wrapper tests — Plan3.5 Bug 3, services/stt.py。

Mock 化 httpx + ffmpeg-via-asyncio.to_thread；不真调 MiMo gateway。
对偶 test_tts_module.py 的 4 个核心 case (happy/retry/4xx/missing-key) +
STT 特有的 transcode path + empty audio rejection。
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from services.stt import (
    _MIME_TO_FORMAT,
    _NATIVE_FORMATS,
    _mime_to_format,
    transcribe,
)


# ----- pure helpers (no mocking needed) -----

def test_mime_to_format_strips_codecs():
    """audio/webm;codecs=opus → 'webm'（drop ;codecs=...）。"""
    assert _mime_to_format("audio/webm;codecs=opus") == "webm"
    assert _mime_to_format("audio/webm; codecs=opus") == "webm"
    assert _mime_to_format("audio/ogg; codecs=opus") == "ogg"


def test_mime_to_format_lookup():
    assert _mime_to_format("audio/wav") == "wav"
    assert _mime_to_format("audio/mpeg") == "mp3"
    assert _mime_to_format("audio/mp4") == "m4a"
    assert _mime_to_format("audio/x-flac") == "flac"


def test_mime_to_format_unknown_defaults_webm():
    """未知 mime → 默认 'webm'，会触发转码路径（webm 不在 _NATIVE_FORMATS）。"""
    assert _mime_to_format("audio/exotic") == "webm"
    assert _mime_to_format("") == "webm"
    assert _mime_to_format(None) == "webm"  # None-safe


def test_native_formats_set_matches_mime_map():
    """_NATIVE_FORMATS 与 _MIME_TO_FORMAT values 是否同步——避免日后改一处忘另一处。

    所有 _MIME_TO_FORMAT.values 中除 "webm" 之外的 format 都应在 _NATIVE_FORMATS。
    """
    mapped = set(_MIME_TO_FORMAT.values())
    needs_transcode = mapped - _NATIVE_FORMATS
    assert needs_transcode == {"webm"}, (
        f"unexpected non-native formats in mime map: {needs_transcode}"
    )


# ----- main wrapper happy / retry / error paths -----


def _fake_ok_response(transcript: str = "你好世界") -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "id": "fake-id",
            "choices": [
                {"message": {"role": "assistant", "content": transcript}}
            ],
        },
        request=httpx.Request("POST", "https://x/v1/chat/completions"),
    )


@pytest.mark.asyncio
async def test_transcribe_happy_native_format(monkeypatch):
    """audio/wav → 不走 transcoding，直接送 MiMo Omni → 返 transcript。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    async def fake_post(*args, **kwargs):
        return _fake_ok_response("hello world")

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        text = await transcribe(b"\x00\x01" * 100, mime="audio/wav")

    assert text == "hello world"


@pytest.mark.asyncio
async def test_transcribe_strips_whitespace(monkeypatch):
    """LLM 可能带换行/空白；wrapper 应 strip 后返回。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    async def fake_post(*args, **kwargs):
        return _fake_ok_response("  你好世界 \n")

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        text = await transcribe(b"\x00\x01" * 100, mime="audio/wav")

    assert text == "你好世界"


@pytest.mark.asyncio
async def test_transcribe_handles_null_content(monkeypatch):
    """choices[0].message.content 为 None（罕见但可能）→ 返空字符串，不抛。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake = httpx.Response(
        status_code=200,
        json={"choices": [{"message": {"role": "assistant", "content": None}}]},
        request=httpx.Request("POST", "https://x/v1/chat/completions"),
    )

    async def fake_post(*args, **kwargs):
        return fake

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        text = await transcribe(b"\x00\x01" * 100, mime="audio/wav")

    assert text == ""


@pytest.mark.asyncio
async def test_transcribe_webm_triggers_transcode(monkeypatch):
    """audio/webm → 调 _transcode_to_wav (asyncio.to_thread)，转 wav 后再上送。

    通过 patch _transcode_to_wav 验证它被调用一次；patch httpx.post 验证
    payload 中 format 字段是 'wav' 而非 'webm'。
    """
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    transcode_calls = {"n": 0}

    def fake_transcode(data: bytes) -> bytes:
        transcode_calls["n"] += 1
        return b"\x52\x49\x46\x46fake_wav_bytes"

    captured_payload = {}

    async def fake_post(self, url, **kwargs):
        captured_payload.update(kwargs.get("json", {}))
        return _fake_ok_response("transcribed")

    with patch("services.stt._transcode_to_wav", side_effect=fake_transcode):
        with patch("httpx.AsyncClient.post", new=fake_post):
            text = await transcribe(b"webm fake bytes", mime="audio/webm;codecs=opus")

    assert text == "transcribed"
    assert transcode_calls["n"] == 1, "transcode should run exactly once for webm"
    # payload 内的 format hint 应为 'wav'（已转码）
    audio_part = captured_payload["messages"][0]["content"][1]
    assert audio_part["type"] == "input_audio"
    assert audio_part["input_audio"]["format"] == "wav"


@pytest.mark.asyncio
async def test_transcribe_native_format_skips_transcode(monkeypatch):
    """audio/ogg / mp3 / wav / flac / m4a 不应触发转码（_transcode_to_wav 不调）。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    transcode_calls = {"n": 0}

    def fake_transcode(data):
        transcode_calls["n"] += 1
        return data

    async def fake_post(*args, **kwargs):
        return _fake_ok_response("ok")

    with patch("services.stt._transcode_to_wav", side_effect=fake_transcode):
        with patch("httpx.AsyncClient.post", side_effect=fake_post):
            for mime in ["audio/ogg", "audio/mpeg", "audio/wav", "audio/flac", "audio/mp4"]:
                await transcribe(b"\x00\x01" * 100, mime=mime)

    assert transcode_calls["n"] == 0


@pytest.mark.asyncio
async def test_transcribe_retry_once_on_network_error(monkeypatch):
    """第一次 NetworkError → retry → 第二次成功，对偶 TTS。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    call_count = {"n": 0}

    async def flaky_post(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.NetworkError("transient")
        return _fake_ok_response("recovered")

    with patch("httpx.AsyncClient.post", side_effect=flaky_post):
        text = await transcribe(b"\x00\x01" * 100, mime="audio/wav")

    assert text == "recovered"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_transcribe_persistent_network_error_raises(monkeypatch):
    """两次都 NetworkError → 抛 httpx.NetworkError（让 endpoint 转 503）。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    async def always_fail(*args, **kwargs):
        raise httpx.NetworkError("down")

    with patch("httpx.AsyncClient.post", side_effect=always_fail):
        with pytest.raises(httpx.NetworkError):
            await transcribe(b"\x00\x01" * 100, mime="audio/wav")


@pytest.mark.asyncio
async def test_transcribe_4xx_no_retry(monkeypatch):
    """API 返 4xx → raise_for_status 抛 HTTPStatusError，不 retry。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake_400 = httpx.Response(
        status_code=400,
        text="bad request",
        request=httpx.Request("POST", "https://x/v1/chat/completions"),
    )
    call_count = {"n": 0}

    async def fake_post(*args, **kwargs):
        call_count["n"] += 1
        return fake_400

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        with pytest.raises(httpx.HTTPStatusError):
            await transcribe(b"\x00\x01" * 100, mime="audio/wav")

    assert call_count["n"] == 1, "4xx must not trigger retry"


@pytest.mark.asyncio
async def test_transcribe_missing_api_key_keyerror(monkeypatch):
    """缺 MIMO_API_KEY → KeyError fail-fast（endpoint 转 503 not configured）。"""
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    with pytest.raises(KeyError):
        await transcribe(b"\x00\x01" * 100, mime="audio/wav")


@pytest.mark.asyncio
async def test_transcribe_empty_audio_raises(monkeypatch):
    """空 bytes → ValueError（让 endpoint 转 400 不让上游浪费 token）。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")
    with pytest.raises(ValueError, match="empty"):
        await transcribe(b"", mime="audio/wav")


@pytest.mark.asyncio
async def test_transcribe_transcode_failure_propagates(monkeypatch):
    """ffmpeg 转码失败 → RuntimeError（让 endpoint 转 422 audio decode failed）。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    def bad_transcode(data):
        raise RuntimeError("ffmpeg: invalid data found when processing input")

    with patch("services.stt._transcode_to_wav", side_effect=bad_transcode):
        with pytest.raises(RuntimeError, match="ffmpeg"):
            await transcribe(b"not audio bytes", mime="audio/webm")


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed_body", [
    {},  # missing choices
    {"choices": []},  # empty choices
    {"choices": [{}]},  # missing message
    {"choices": [{"message": {}}]},  # missing content key
    {"choices": [{"message": {"role": "assistant"}}]},  # content key missing alt
    None,  # not a dict at all
])
async def test_transcribe_malformed_response_raises_httperror(monkeypatch, malformed_body):
    """上游 200 但 schema 偏移 → 转成 httpx.HTTPError（不是 KeyError！）。

    保护点：endpoint 层 `except KeyError` 是给 missing API key 用的，
    不能让上游 schema 变更也走那条路径误报 "not configured"。
    """
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    fake = httpx.Response(
        status_code=200,
        json=malformed_body,
        request=httpx.Request("POST", "https://x/v1/chat/completions"),
    )

    async def fake_post(*args, **kwargs):
        return fake

    with patch("httpx.AsyncClient.post", side_effect=fake_post):
        with pytest.raises(httpx.HTTPError):
            await transcribe(b"\x00\x01" * 100, mime="audio/wav")


@pytest.mark.asyncio
async def test_transcribe_ffmpeg_timeout_raises_runtimeerror(monkeypatch):
    """ffmpeg 转码超时 → subprocess.TimeoutExpired 必须被转成 RuntimeError。

    保护点：subprocess.TimeoutExpired 不是 RuntimeError 子类（继承
    SubprocessError → Exception），如果 wrapper 不显式转换，endpoint 层
    `except RuntimeError` 接不住 → 升级到 500（generic server error），
    诊断噪声。
    """
    import subprocess
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")

    def slow_transcode(data):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)

    # 直调 _transcode_to_wav 不会触发 — 这里 monkey-patch subprocess.run 里抛
    # （拦在 _transcode_to_wav 内部 try/except 上游）
    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)

    with patch("services.stt.subprocess.run", side_effect=fake_run):
        with patch("services.stt.shutil.which", return_value="/fake/ffmpeg"):
            with pytest.raises(RuntimeError, match="timed out"):
                await transcribe(b"webm bytes", mime="audio/webm")


@pytest.mark.asyncio
async def test_transcribe_payload_shape(monkeypatch):
    """验证发送 payload 的 OpenAI multimodal schema 关键字段无 drift。"""
    monkeypatch.setenv("MIMO_API_KEY", "fake-key")
    monkeypatch.setenv("MIMO_OMNI_MODEL", "custom-model-name")

    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["json"] = kwargs.get("json", {})
        return _fake_ok_response("x")

    with patch("httpx.AsyncClient.post", new=fake_post):
        await transcribe(b"\x00\x01" * 50, mime="audio/wav")

    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    payload = captured["json"]
    assert payload["model"] == "custom-model-name"
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    assert msg["content"][0]["type"] == "text"
    audio_part = msg["content"][1]
    assert audio_part["type"] == "input_audio"
    # base64 应是字符串，不是 bytes
    assert isinstance(audio_part["input_audio"]["data"], str)
    assert audio_part["input_audio"]["format"] == "wav"
