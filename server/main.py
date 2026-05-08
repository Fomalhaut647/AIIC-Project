"""FastAPI app for MiMo web chat."""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.mimo import CHAT_MODELS, MIMO_BASE_URL

load_dotenv()

MIMO_API_KEY = os.environ.get("MIMO_API_KEY")
if not MIMO_API_KEY:
    raise RuntimeError(
        "MIMO_API_KEY is required. Put it in .env or export it before launching."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10, read=600, write=10, pool=10)
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = True


app = FastAPI(title="AIIC MiMo Chat", version="1.0.0", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models")
async def list_models() -> dict[str, list[dict[str, str]]]:
    return {"data": [{"id": m, "object": "model", "owned_by": "xiaomi"} for m in CHAT_MODELS]}


WEB_DIR = Path(__file__).resolve().parent.parent / "web"

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@app.post("/api/chat")
async def chat(req: ChatRequest, client: httpx.AsyncClient = Depends(get_http_client)):
    if req.model not in CHAT_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    if not req.stream:
        raise HTTPException(status_code=400, detail="stream=false is not supported in v1")

    upstream_payload = req.model_dump()

    async def event_stream():
        try:
            async with client.stream(
                "POST",
                f"{MIMO_BASE_URL}/chat/completions",
                json=upstream_payload,
                headers={
                    "Authorization": f"Bearer {MIMO_API_KEY}",
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                },
            ) as upstream:
                if upstream.status_code >= 400:
                    body = await upstream.aread()
                    yield (
                        f"event: error\n"
                        f"data: {{\"status\":{upstream.status_code},"
                        f"\"body\":{json_str(body)}}}\n\n"
                    ).encode()
                    return
                async for chunk in upstream.aiter_raw():
                    if chunk:
                        yield chunk
        except Exception as exc:
            yield (
                f"event: error\n"
                f"data: {{\"status\":502,\"body\":\"upstream_failure: {type(exc).__name__}\"}}\n\n"
            ).encode()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


def json_str(b: bytes) -> str:
    """把上游错误体安全编码进 SSE data 行的 JSON 字符串。"""
    try:
        return json.dumps(b.decode("utf-8", errors="replace"))
    except Exception:
        return json.dumps(repr(b))


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
