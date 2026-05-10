"""MiMo Omni STT — Plan3.5 Bug 3 backend.

走 OpenAI 兼容 `/v1/chat/completions` + multimodal `input_audio` 字段，让
`mimo-v2-omni` 多模态模型做语音转录。MiMo gateway 没有 `/v1/audio/transcriptions`
独立 endpoint（实测 404），但 omni 接受 `input_audio` 多模态输入。

实测 server 端解码支持 mp3/flac/m4a/wav/ogg；**不支持 webm/opus**（Chrome
MediaRecorder 默认输出格式）。所以这里在 wrapper 内置 ffmpeg 转码：webm/任意
未直接支持的容器 → wav (PCM 16kHz mono) 后再上传。需要 ffmpeg binary 在
$PATH（pixi 已 add）。

错误处理参照 services/tts.py：
- httpx.NetworkError 触发 retry once（瞬态网络毛刺）
- httpx.TimeoutException 不 retry（服务端慢，retry 只放大）
- HTTP 4xx/5xx 不 retry，让 endpoint 转 503/422
- 缺 MIMO_API_KEY → KeyError fail-fast，endpoint 转 503 "not configured"
"""
from __future__ import annotations

import asyncio
import base64
import os
import shutil
import subprocess

import httpx

# MiMo Omni 实际能解码的格式（错误信息明示）；其余 mime 需 ffmpeg 转码到 wav。
_NATIVE_FORMATS = {"mp3", "flac", "m4a", "wav", "ogg"}

# mime → format hint 映射；server 似乎以 magic bytes 嗅探，format 仅是 hint。
_MIME_TO_FORMAT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "audio/webm": "webm",
    "audio/opus": "ogg",
}

# 默认转录提示词；prompt 控制输出干净度（避免 "音频内容是..." 前缀）。
_TRANSCRIBE_PROMPT = (
    "你是语音转录引擎。把音频内容准确转录为简体中文文本，"
    "只输出原始转录结果本身，不要任何前缀、后缀、解释、引号或多余标点。"
    "如音频无清晰人声，输出空字符串。"
)


def _mime_to_format(mime: str) -> str:
    """从 mime 字符串提取 format hint（去掉 ;codecs=... 部分）。

    未知 mime 默认 'webm'（最常见的 Chrome MediaRecorder 输出，会触发转码路径）。
    """
    base = (mime or "").split(";", 1)[0].strip().lower()
    return _MIME_TO_FORMAT.get(base, "webm")


def _transcode_to_wav(audio_bytes: bytes) -> bytes:
    """ffmpeg 把任意支持的容器转 PCM WAV (16kHz mono 16-bit)。

    16kHz mono 是 ASR 业界默认；省带宽 + omni 解码无差异。

    raises:
        RuntimeError: ffmpeg 二进制不存在 / 转码失败（输入非音频/损坏） / 超时。
            注意：`subprocess.TimeoutExpired` 不是 RuntimeError 子类，必须显式
            转换，否则 endpoint `except RuntimeError` 接不住 → 500 误报。
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg binary not found in $PATH")

    # -i pipe:0 stdin / -f wav -ar 16000 -ac 1 / pipe:1 stdout
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "wav", "-ar", "16000", "-ac", "1",
                "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        # subprocess.run timeout 已 internal kill child 并 reap，这里只需转 exception 类型
        raise RuntimeError("ffmpeg transcode timed out") from e
    if proc.returncode != 0:
        # ffmpeg stderr 通常含具体 reason（unknown format / corrupt header / …）
        err = proc.stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ffmpeg transcode failed: {err}")
    return proc.stdout


async def transcribe(
    audio_bytes: bytes,
    mime: str = "audio/webm",
    *,
    timeout: float = 60.0,
    language_hint: str = "zh-CN",
) -> str:
    """Plan3.5 Bug 3 — 调 MiMo Omni 做 STT。

    Args:
        audio_bytes: 原始音频字节（任意常见容器；webm/opus 会先转 wav）。
        mime: 音频 mime（如 "audio/webm; codecs=opus"）；用于决定是否转码。
        timeout: 单次 HTTP 调用超时（默认 60s；ASR 比 TTS 慢）。
        language_hint: 目前未送给 server（Omni 自动检测），保留参数以备后续 provider 切换。

    Returns:
        转录得到的文本（已 strip 空白）；可能为空字符串（音频无清晰人声）。

    Raises:
        ValueError: audio_bytes 为空。
        RuntimeError: ffmpeg 转码失败（输入非音频或损坏）。
        httpx.HTTPError: 上游 HTTP 错误（4xx/5xx/network/timeout）。
        KeyError: 缺 MIMO_API_KEY 配置。
    """
    if not audio_bytes:
        raise ValueError("audio_bytes is empty")

    api_key = os.environ["MIMO_API_KEY"]  # 缺 → KeyError fail-fast
    base_url = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_OMNI_MODEL", "mimo-v2-omni")

    fmt = _mime_to_format(mime)
    if fmt not in _NATIVE_FORMATS:
        # webm/opus 等 → 转 wav。CPU-bound subprocess，offload 到 thread。
        audio_bytes = await asyncio.to_thread(_transcode_to_wav, audio_bytes)
        fmt = "wav"

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _TRANSCRIBE_PROMPT},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": fmt}},
                ],
            }
        ],
        # 控制输出长度上限，省 token；中文转录 60s 音频 ≈ 200 chars，1024 充裕。
        "max_tokens": 1024,
        # 不传 temperature；omni reasoning 模型默认 deterministic 较好。
    }

    async def _call() -> str:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            # OpenAI schema：choices[0].message.content；reasoning_content 不取（CoT 泄露）
            # 上游可能返 200 但 body 不可解析或 schema 偏移：
            #   - r.json() ValueError (JSONDecodeError) — body 非 JSON
            #   - data["choices"]... KeyError/IndexError/TypeError — 字段缺失或类型变更
            # 必须区分这些 KeyError 与 endpoint 层 `os.environ["MIMO_API_KEY"]` 的 KeyError
            # —— 后者表示 "not configured"，前者是 "upstream malformed"，语义截然不同。
            # 转成 httpx.RemoteProtocolError（httpx.HTTPError 子类）→ endpoint 捕获为 503
            # "upstream unavailable"，运维诊断不被误导。
            try:
                data = r.json()
                content = data["choices"][0]["message"]["content"] or ""
            except (ValueError, KeyError, IndexError, TypeError) as e:
                raise httpx.RemoteProtocolError(
                    "MiMo Omni returned 200 but response is malformed "
                    "(non-JSON body or missing choices/message/content)"
                ) from e
            return content.strip()

    try:
        return await _call()
    except httpx.NetworkError:
        return await _call()  # retry once on transient network error
