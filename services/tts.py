"""MiMo TTS — Plan3 G3 (Spec E §9.1).

OpenAI 兼容 POST /v1/audio/speech；返 audio bytes（mp3）。
Retry once on httpx.NetworkError；HTTP 4xx/5xx 不 retry，让 endpoint 层处理。
"""
from __future__ import annotations

import os

import httpx


async def synthesize_speech(
    text: str,
    voice: str = "default",
    *,
    timeout: float = 30.0,
) -> bytes:
    """Spec E §9.1 — 调 MiMo audio.speech。
    成功返 audio bytes；失败 raise httpx 异常给上层。

    Note: 仅 httpx.NetworkError 触发 retry；httpx.TimeoutException 不 retry
    （timeout 通常意味服务端慢而非瞬态毛刺，retry 只会级联放大）。
    """
    api_key = os.environ["MIMO_API_KEY"]  # 缺 → KeyError fail-fast
    base_url = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-tts")

    url = f"{base_url}/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": text, "voice": voice, "response_format": "mp3"}

    async def _call() -> bytes:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.content

    try:
        return await _call()
    except httpx.NetworkError:
        return await _call()  # retry once on transient network error
