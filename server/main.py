"""FastAPI app for MiMo web chat."""
from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from server.mimo import CHAT_MODELS

load_dotenv()

MIMO_API_KEY = os.environ.get("MIMO_API_KEY")
if not MIMO_API_KEY:
    raise RuntimeError(
        "MIMO_API_KEY is required. Put it in .env or export it before launching."
    )


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = True


app = FastAPI(title="AIIC MiMo Chat", version="1.0.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models")
async def list_models() -> dict[str, list[dict[str, str]]]:
    return {"data": [{"id": m, "object": "model", "owned_by": "xiaomi"} for m in CHAT_MODELS]}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.model not in CHAT_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    if not req.stream:
        raise HTTPException(status_code=400, detail="stream=false is not supported in v1")
    raise HTTPException(status_code=501, detail="streaming not yet implemented")
