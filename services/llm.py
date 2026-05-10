"""DeepSeek (OpenAI-compatible) async client with JSON repair + fallback."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import TypeVar
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from services.prompts import JSON_OUTPUT_INSTRUCTION, JSON_REPAIR_INSTRUCTION

load_dotenv()

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

LOG_PATH = Path("logs/llm.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_logger = logging.getLogger("aiic.llm")
if not _logger.handlers:
    h = logging.FileHandler(LOG_PATH, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(h)
    _logger.setLevel(logging.INFO)

T = TypeVar("T", bound=BaseModel)


class LLMSchemaError(Exception):
    pass


_NETWORK_RETRY_DELAY_S = 5.0
_NETWORK_RETRYABLE = (
    httpx.TimeoutException,  # 包含 ReadTimeout / ConnectTimeout / WriteTimeout / PoolTimeout
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


async def _post_chat(messages, temperature, max_tokens, *, json_mode: bool = False):
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
               "Content-Type": "application/json"}
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                                 headers=headers, json=body)
        resp.raise_for_status()
        return resp


async def _post_chat_with_retry(messages, temperature, max_tokens, *, json_mode: bool = False):
    """Spec §7: 网络超时 / ConnectError → sleep 5s 后 retry once；仍失败 → 抛出供上层 fallback。"""
    try:
        return await _post_chat(messages, temperature, max_tokens, json_mode=json_mode)
    except _NETWORK_RETRYABLE:
        await asyncio.sleep(_NETWORK_RETRY_DELAY_S)
        return await _post_chat(messages, temperature, max_tokens, json_mode=json_mode)


def _extract_content(resp) -> str:
    return resp.json()["choices"][0]["message"]["content"]


async def call_deepseek(
    messages: list[dict],
    *,
    response_schema: type[T] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    fallback: T | str | None = None,
) -> T | str:
    """See Spec A §3.1 for full contract."""
    started = time.time()
    msgs = [dict(m) for m in messages]
    role = msgs[0].get("content", "")[:40] if msgs else ""

    if response_schema is not None:
        # 注入 JSON 输出要求
        schema_json = json.dumps(response_schema.model_json_schema(), ensure_ascii=False)
        msgs[-1]["content"] = (msgs[-1]["content"]
                               + JSON_OUTPUT_INSTRUCTION.format(schema_json=schema_json))
        try:
            resp = await _post_chat_with_retry(msgs, temperature, max_tokens, json_mode=True)
        except _NETWORK_RETRYABLE:
            if fallback is not None:
                _log(role, 0, False, True, started)
                return fallback
            raise
        content = _extract_content(resp)
        try:
            parsed = response_schema.model_validate_json(content)
            _log(role, len(content), False, False, started)
            return parsed
        except (json.JSONDecodeError, ValidationError) as e:
            # repair retry
            repair_msg = {
                "role": "user",
                "content": JSON_REPAIR_INSTRUCTION.format(
                    original_output=content, error_message=str(e),
                ),
            }
            try:
                resp2 = await _post_chat_with_retry(
                    [*msgs, {"role": "assistant", "content": content}, repair_msg],
                    temperature, max_tokens, json_mode=True,
                )
            except _NETWORK_RETRYABLE:
                if fallback is not None:
                    _log(role, 0, True, True, started)
                    return fallback
                raise
            content2 = _extract_content(resp2)
            try:
                parsed = response_schema.model_validate_json(content2)
                _log(role, len(content2), True, False, started)
                return parsed
            except (json.JSONDecodeError, ValidationError):
                if fallback is not None:
                    _log(role, len(content2), True, True, started)
                    return fallback
                raise LLMSchemaError(f"repair failed: {content2[:200]}")
    else:
        try:
            resp = await _post_chat_with_retry(msgs, temperature, max_tokens, json_mode=False)
        except _NETWORK_RETRYABLE:
            if fallback is not None:
                _log(role, 0, False, True, started)
                return fallback
            raise
        content = _extract_content(resp)
        _log(role, len(content), False, False, started)
        return content


def _log(role: str, resp_chars: int, repair: bool, fallback: bool, started: float):
    duration_ms = int((time.time() - started) * 1000)
    _logger.info(
        f"role={role!r} | resp_chars={resp_chars} | repair={repair} "
        f"| fallback={fallback} | duration_ms={duration_ms}"
    )
