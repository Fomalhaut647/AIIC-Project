"""Constants for upstream MiMo OpenAI-compatible API."""
from __future__ import annotations

MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

CHAT_MODELS: tuple[str, ...] = (
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2-pro",
    "mimo-v2-omni",
)
