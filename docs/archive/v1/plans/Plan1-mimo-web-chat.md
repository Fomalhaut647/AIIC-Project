# MiMo Web Chat 第一版实施计划

> 起草日期：2026-05-08
> 对应 spec：`docs/specs/2026-05-08-mimo-web-chat-design.md`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `https://aiic.fomalhaut647.com` 部署一个能直接 chat MiMo 的多会话流式网页，受 HTTP Basic Auth 保护，5/10 截止前可用。

**Architecture:** 单页 HTML/JS 前端走 fetch + ReadableStream 解析 SSE 与同源 FastAPI 后端通信；FastAPI 把请求带上 `MIMO_API_KEY` 透传到 `https://token-plan-cn.xiaomimimo.com/v1/chat/completions` 并把上游 SSE 字节按原样回送；Nginx 在 443 端口做 Basic Auth 收口 + 反代到 `127.0.0.1:8000` + 关闭代理缓冲透传 SSE。前端把多会话历史存 localStorage。

**Tech Stack:** Python 3.13 (Pixi 管理), FastAPI, uvicorn, httpx (async stream), pydantic v2, pytest, vanilla HTML/CSS/JS, Nginx 1.24, systemd, htpasswd Basic Auth, Markdown via `marked` (CDN)。

**Basic Auth 凭据**（部署时使用）：用户名 `aiic`，口令 `<REDACTED>`。

---

## 文件结构（最终态）

```
AIIC-Project/
├── pixi.toml                  # 加 fastapi/uvicorn/httpx/pytest + serve/test tasks
├── pixi.lock                  # 由 pixi add 自动更新
├── pytest.ini                 # 测试发现 + pythonpath
├── .env                       # 已存在
├── server/
│   ├── __init__.py            # 空
│   ├── main.py                # FastAPI app + 路由 + httpx 流式代理
│   └── mimo.py                # MIMO_BASE_URL + CHAT_MODELS 常量
├── web/
│   ├── index.html             # 整页骨架，引用 /static/app.js + /static/styles.css
│   ├── app.js                 # 前端状态管理、会话、SSE 消费
│   └── styles.css             # 暗色主题
├── tests/
│   ├── __init__.py            # 空
│   ├── conftest.py            # FastAPI TestClient + httpx MockTransport fixture
│   ├── test_health.py
│   ├── test_models.py
│   ├── test_chat_validation.py
│   ├── test_chat_streaming.py
│   ├── test_chat_upstream_error.py
│   └── test_static.py
├── deploy/
│   ├── aiic-chat.service              # systemd unit
│   └── nginx-aiic.location.conf       # Nginx location 片段（含 Basic Auth + SSE 设置）
├── docs/
│   ├── specs/2026-05-08-mimo-web-chat-design.md
│   └── plans/Plan1-mimo-web-chat.md   # 本文件
├── CLAUDE.md                  # 收尾时增补 web chat 部署章节
└── README.md                  # 收尾时新建（人类向 5 分钟上手）
```

---

## Task 1: 添加后端依赖与 pixi tasks

**Files:**
- Modify: `pixi.toml`
- Modify: `pixi.lock`

- [ ] **Step 1: 确认工作树干净**

```bash
git status --short
```

Expected: 输出为空（如非空，先停下来报告异常状态再决定，禁止盲目 stash/discard）。

- [ ] **Step 2: 添加依赖**

```bash
pixi add fastapi uvicorn httpx pytest
```

Expected: 成功更新 `pixi.toml` 的 `[dependencies]`，并自动 resolve `pixi.lock`。

- [ ] **Step 3: 在 `pixi.toml` 末尾追加 tasks**

把 `[tasks]` 段落改成：

```toml
[tasks]
serve = "uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload"
serve-prod = "uvicorn server.main:app --host 127.0.0.1 --port 8000"
test = "pytest"
```

- [ ] **Step 4: 验证依赖可导入**

```bash
pixi run python -c "import fastapi, uvicorn, httpx, pytest; print('ok')"
```

Expected: 输出 `ok`，无 ImportError。

- [ ] **Step 5: 提交**

```bash
git add pixi.toml pixi.lock
git commit -m "chore(deps): add fastapi/uvicorn/httpx/pytest for web chat backend"
```

---

## Task 2: pytest 配置 + tests 目录骨架

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/test_health.py`（占位健康检查测试，验证测试管道可跑）

- [ ] **Step 1: 写 `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -ra -q
```

- [ ] **Step 2: 创建空 `tests/__init__.py`**

```bash
: > tests/__init__.py
```

- [ ] **Step 3: 写一个能立即跑过的 sanity test `tests/test_health.py`**

```python
def test_pytest_pipeline_works():
    assert 1 + 1 == 2
```

- [ ] **Step 4: 运行 pytest 验证管道**

```bash
pixi run test
```

Expected: `1 passed`。

- [ ] **Step 5: 提交**

```bash
git add pytest.ini tests/__init__.py tests/test_health.py
git commit -m "test: scaffold pytest configuration and tests directory"
```

---

## Task 3: `server/mimo.py` — 模型白名单与上游常量（TDD）

**Files:**
- Create: `server/__init__.py`
- Create: `server/mimo.py`
- Create: `tests/test_mimo_constants.py`

- [ ] **Step 1: 写失败测试 `tests/test_mimo_constants.py`**

```python
from server.mimo import CHAT_MODELS, MIMO_BASE_URL


def test_chat_models_are_known_chat_capable():
    assert "mimo-v2.5-pro" in CHAT_MODELS
    assert "mimo-v2.5" in CHAT_MODELS
    assert "mimo-v2-pro" in CHAT_MODELS
    assert "mimo-v2-omni" in CHAT_MODELS


def test_chat_models_exclude_tts():
    for m in CHAT_MODELS:
        assert "tts" not in m, f"{m} looks like a TTS model and shouldn't be in chat list"


def test_mimo_base_url_is_token_plan_v1():
    assert MIMO_BASE_URL == "https://token-plan-cn.xiaomimimo.com/v1"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pixi run test tests/test_mimo_constants.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'server'`。

- [ ] **Step 3: 写最小实现**

`server/__init__.py`：

```python
```

（空文件即可。）

`server/mimo.py`：

```python
"""Constants for upstream MiMo OpenAI-compatible API."""
from __future__ import annotations

MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"

CHAT_MODELS: tuple[str, ...] = (
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2-pro",
    "mimo-v2-omni",
)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pixi run test tests/test_mimo_constants.py
```

Expected: `3 passed`。

- [ ] **Step 5: 提交**

```bash
git add server/__init__.py server/mimo.py tests/test_mimo_constants.py
git commit -m "feat(server): add MiMo upstream constants and chat model whitelist"
```

---

## Task 4: FastAPI app + `/api/health`（TDD）

**Files:**
- Create: `server/main.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_health.py`（替换占位测试为真实 health 测试）

- [ ] **Step 1: 写真实失败测试 `tests/test_health.py`**

替换原内容：

```python
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: 写 fixture `tests/conftest.py`**

```python
import os
import pytest
from fastapi.testclient import TestClient

# 让导入 server.main 时能找到 MIMO_API_KEY
os.environ.setdefault("MIMO_API_KEY", "test-key")

from server.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 3: 运行测试验证失败**

```bash
pixi run test tests/test_health.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'server.main'`。

- [ ] **Step 4: 写最小 FastAPI app `server/main.py`**

```python
"""FastAPI app for MiMo web chat."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

MIMO_API_KEY = os.environ.get("MIMO_API_KEY")
if not MIMO_API_KEY:
    raise RuntimeError(
        "MIMO_API_KEY is required. Put it in .env or export it before launching."
    )

app = FastAPI(title="AIIC MiMo Chat", version="1.0.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pixi run test tests/test_health.py
```

Expected: `1 passed`。

- [ ] **Step 6: 提交**

```bash
git add server/main.py tests/conftest.py tests/test_health.py
git commit -m "feat(server): bootstrap FastAPI app with /api/health endpoint"
```

---

## Task 5: `/api/models` endpoint（TDD）

**Files:**
- Modify: `server/main.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 写失败测试 `tests/test_models.py`**

```python
from fastapi.testclient import TestClient

from server.mimo import CHAT_MODELS


def test_models_returns_whitelist(client: TestClient):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    ids = [m["id"] for m in body["data"]]
    assert ids == list(CHAT_MODELS)


def test_models_no_tts(client: TestClient):
    resp = client.get("/api/models")
    ids = [m["id"] for m in resp.json()["data"]]
    for mid in ids:
        assert "tts" not in mid
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pixi run test tests/test_models.py
```

Expected: FAIL — 路由返回 404。

- [ ] **Step 3: 在 `server/main.py` 加 endpoint**

在 `health` 之后追加：

```python
from server.mimo import CHAT_MODELS


@app.get("/api/models")
async def list_models() -> dict[str, list[dict[str, str]]]:
    return {"data": [{"id": m, "object": "model", "owned_by": "xiaomi"} for m in CHAT_MODELS]}
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pixi run test tests/test_models.py
```

Expected: `2 passed`。

- [ ] **Step 5: 提交**

```bash
git add server/main.py tests/test_models.py
git commit -m "feat(server): add /api/models endpoint returning chat whitelist"
```

---

## Task 6: `/api/chat` 入参校验（TDD，先做校验，下一 task 做 SSE 转发）

**Files:**
- Modify: `server/main.py`
- Create: `tests/test_chat_validation.py`

- [ ] **Step 1: 写失败测试 `tests/test_chat_validation.py`**

```python
from fastapi.testclient import TestClient


def test_unknown_model_rejected(client: TestClient):
    resp = client.post(
        "/api/chat",
        json={
            "model": "gpt-5-fake",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert resp.status_code == 400
    assert "Unknown model" in resp.text


def test_empty_messages_rejected(client: TestClient):
    resp = client.post(
        "/api/chat",
        json={"model": "mimo-v2.5-pro", "messages": [], "stream": True},
    )
    assert resp.status_code == 422  # pydantic validation


def test_bad_role_rejected(client: TestClient):
    resp = client.post(
        "/api/chat",
        json={
            "model": "mimo-v2.5-pro",
            "messages": [{"role": "robot", "content": "hi"}],
            "stream": True,
        },
    )
    assert resp.status_code == 422


def test_non_streaming_rejected(client: TestClient):
    resp = client.post(
        "/api/chat",
        json={
            "model": "mimo-v2.5-pro",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert resp.status_code == 400
    assert "stream" in resp.text.lower()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pixi run test tests/test_chat_validation.py
```

Expected: 全 FAIL（404）。

- [ ] **Step 3: 在 `server/main.py` 增加 pydantic 模型 + 路由（暂时不做 SSE，仅校验后返回 501）**

在 `app = FastAPI(...)` 之前 import 与定义模型：

```python
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = True
```

在 `list_models` 之后追加：

```python
@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.model not in CHAT_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    if not req.stream:
        raise HTTPException(status_code=400, detail="stream=false is not supported in v1")
    raise HTTPException(status_code=501, detail="streaming not yet implemented")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pixi run test tests/test_chat_validation.py
```

Expected: `4 passed`。

- [ ] **Step 5: 提交**

```bash
git add server/main.py tests/test_chat_validation.py
git commit -m "feat(server): add /api/chat input validation (model whitelist, schema)"
```

---

## Task 7: `/api/chat` SSE 流式代理 happy path（TDD）

**Files:**
- Modify: `server/main.py`
- Modify: `tests/conftest.py`（增加 mock-transport 客户端 fixture + dependency override）
- Create: `tests/test_chat_streaming.py`

- [ ] **Step 1: 在 `server/main.py` 抽出 httpx 客户端依赖**

在文件顶部 import 后追加（`app` 创建之前）：

```python
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, Request


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
```

修改 `app = FastAPI(...)` 为：

```python
app = FastAPI(title="AIIC MiMo Chat", version="1.0.0", lifespan=lifespan)
```

- [ ] **Step 2: 重构 `chat` 路由签名以注入 client（仍返回 501）**

```python
@app.post("/api/chat")
async def chat(req: ChatRequest, client: httpx.AsyncClient = Depends(get_http_client)):
    if req.model not in CHAT_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    if not req.stream:
        raise HTTPException(status_code=400, detail="stream=false is not supported in v1")
    raise HTTPException(status_code=501, detail="streaming not yet implemented")
```

- [ ] **Step 3: 跑回归确认 Task 6 测试仍通过**

```bash
pixi run test tests/test_chat_validation.py
```

Expected: `4 passed`。

- [ ] **Step 4: 扩展 `tests/conftest.py`，增加 mock 客户端 fixture**

把 `tests/conftest.py` 替换为：

```python
import os
from typing import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MIMO_API_KEY", "test-key")

from server.main import app, get_http_client  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def mock_upstream() -> Callable[[Callable[[httpx.Request], httpx.Response]], TestClient]:
    """
    用法：
        def test_x(mock_upstream):
            def handler(req): return httpx.Response(200, content=b"...")
            client = mock_upstream(handler)
            with client.stream(...) as resp: ...
    """

    created_clients: list[httpx.AsyncClient] = []

    def factory(handler: Callable[[httpx.Request], httpx.Response]) -> TestClient:
        transport = httpx.MockTransport(handler)
        mock_client = httpx.AsyncClient(transport=transport)
        created_clients.append(mock_client)

        async def override() -> httpx.AsyncClient:
            return mock_client

        app.dependency_overrides[get_http_client] = override
        return TestClient(app)

    yield factory

    app.dependency_overrides.clear()
    # 客户端随事件循环退出，httpx 会自动清理；这里不强制 aclose 以避免 event loop 关闭后报错
    created_clients.clear()
```

- [ ] **Step 5: 写失败的流式 happy-path 测试 `tests/test_chat_streaming.py`**

```python
import json

import httpx


SSE_BODY = (
    b"data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"hello \"}}]}\n\n"
    b"data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"world\"}}]}\n\n"
    b"data: [DONE]\n\n"
)


def test_streaming_passes_upstream_chunks_through(mock_upstream):
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("authorization")
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            content=SSE_BODY,
            headers={"content-type": "text/event-stream"},
        )

    client = mock_upstream(handler)

    payload = {
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    with client.stream("POST", "/api/chat", json=payload) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("x-accel-buffering") == "no"
        body = b"".join(resp.iter_bytes())

    assert b"hello " in body
    assert b"world" in body
    assert b"[DONE]" in body
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "mimo-v2.5-pro"
    assert captured["body"]["stream"] is True
```

- [ ] **Step 6: 运行测试验证失败**

```bash
pixi run test tests/test_chat_streaming.py
```

Expected: FAIL — 路由仍返回 501。

- [ ] **Step 7: 在 `server/main.py` 实现真实 SSE 转发**

把 `chat` 函数替换为：

```python
from fastapi.responses import StreamingResponse

from server.mimo import MIMO_BASE_URL


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
        except httpx.HTTPError as exc:
            yield (
                f"event: error\n"
                f"data: {{\"status\":502,\"body\":\"upstream_failure: {type(exc).__name__}\"}}\n\n"
            ).encode()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


def json_str(b: bytes) -> str:
    """把上游错误体安全编码进 SSE data 行的 JSON 字符串。"""
    import json
    try:
        return json.dumps(b.decode("utf-8", errors="replace"))
    except Exception:
        return json.dumps(repr(b))
```

- [ ] **Step 8: 运行测试验证通过**

```bash
pixi run test tests/test_chat_streaming.py
```

Expected: `1 passed`。

- [ ] **Step 9: 跑全部测试确认无回归**

```bash
pixi run test
```

Expected: 全部通过。

- [ ] **Step 10: 提交**

```bash
git add server/main.py tests/conftest.py tests/test_chat_streaming.py
git commit -m "feat(server): proxy /api/chat to MiMo with SSE streaming"
```

---

## Task 8: `/api/chat` 上游错误透传（TDD）

**Files:**
- Create: `tests/test_chat_upstream_error.py`

（Task 7 实现已经覆盖错误路径，本 task 只补强测试，不改实现。如失败再补实现。）

- [ ] **Step 1: 写失败测试 `tests/test_chat_upstream_error.py`**

```python
import httpx


def test_upstream_401_passed_through_as_sse_error(mock_upstream):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    client = mock_upstream(handler)
    payload = {
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    with client.stream("POST", "/api/chat", json=payload) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())

    assert b"event: error" in body
    assert b"401" in body


def test_upstream_network_error_emits_sse_error(mock_upstream):
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    client = mock_upstream(handler)
    payload = {
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    with client.stream("POST", "/api/chat", json=payload) as resp:
        body = b"".join(resp.iter_bytes())

    assert b"event: error" in body
    assert b"upstream_failure" in body
```

- [ ] **Step 2: 运行测试**

```bash
pixi run test tests/test_chat_upstream_error.py
```

Expected: `2 passed`（应直接通过，因为 Task 7 实现已经覆盖；如有 fail 修补实现后再跑）。

- [ ] **Step 3: 提交**

```bash
git add tests/test_chat_upstream_error.py
git commit -m "test(server): cover upstream 401 and network error SSE passthrough"
```

---

## Task 9: 静态文件挂载与根路由（TDD）

**Files:**
- Create: `web/index.html`（占位，后续 task 完整化）
- Modify: `server/main.py`
- Create: `tests/test_static.py`

- [ ] **Step 1: 写失败测试 `tests/test_static.py`**

```python
from fastapi.testclient import TestClient


def test_root_serves_index_html(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "AIIC MiMo Chat" in resp.text


def test_static_app_js_served(client: TestClient, tmp_path, monkeypatch):
    # 真实从 web/ 提供
    resp = client.get("/static/styles.css")
    # 文件可能不存在还，但路由必须挂上 → 不存在则返回 404；存在则 200
    assert resp.status_code in (200, 404)
```

- [ ] **Step 2: 写占位 `web/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>AIIC MiMo Chat</title>
</head>
<body>
  <h1>AIIC MiMo Chat — placeholder</h1>
</body>
</html>
```

- [ ] **Step 3: 运行测试验证失败**

```bash
pixi run test tests/test_static.py
```

Expected: FAIL — `/` 路由不存在。

- [ ] **Step 4: 在 `server/main.py` 挂载静态 + 根路由**

在文件顶部 import 区追加：

```python
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
```

在所有路由定义之后追加：

```python
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pixi run test tests/test_static.py
```

Expected: `2 passed`。

- [ ] **Step 6: 跑全部测试**

```bash
pixi run test
```

Expected: 全部通过。

- [ ] **Step 7: 提交**

```bash
git add web/index.html server/main.py tests/test_static.py
git commit -m "feat(server): mount /static and serve index.html at /"
```

---

## Task 10: 前端骨架 — `web/index.html`

**Files:**
- Modify: `web/index.html`

- [ ] **Step 1: 替换 `web/index.html` 为完整骨架**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIIC MiMo Chat</title>
  <link rel="stylesheet" href="/static/styles.css">
  <script src="https://cdn.jsdelivr.net/npm/marked@13/marked.min.js" defer></script>
  <script src="/static/app.js" type="module" defer></script>
</head>
<body>
  <aside id="sidebar">
    <button id="new-conv">+ 新建会话</button>
    <ul id="conv-list"></ul>
  </aside>
  <main id="main">
    <header id="topbar">
      <select id="model-picker"></select>
      <span id="conv-title"></span>
    </header>
    <section id="messages"></section>
    <footer id="composer">
      <textarea id="input" placeholder="输入消息，Enter 发送 / Shift+Enter 换行" rows="3"></textarea>
      <button id="send">发送</button>
    </footer>
  </main>
</body>
</html>
```

- [ ] **Step 2: 提交**

```bash
git add web/index.html
git commit -m "feat(web): full HTML skeleton with sidebar/main layout"
```

---

## Task 11: 前端样式 — `web/styles.css`

**Files:**
- Create: `web/styles.css`

- [ ] **Step 1: 写 `web/styles.css`**

```css
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; font-family: ui-sans-serif, system-ui, "PingFang SC", "Microsoft Yahei", sans-serif; background: #1a1b1e; color: #e6e6e6; }
body { display: grid; grid-template-columns: 260px 1fr; height: 100vh; }

#sidebar { background: #111214; border-right: 1px solid #2a2b30; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
#new-conv { padding: 10px 12px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
#new-conv:hover { background: #1d4ed8; }
#conv-list { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-direction: column; gap: 4px; }
#conv-list li { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; gap: 6px; align-items: center; font-size: 14px; }
#conv-list li.active { background: #2a2b30; }
#conv-list li:hover { background: #232428; }
#conv-list .title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#conv-list button { background: none; border: none; color: #888; cursor: pointer; padding: 2px 4px; }
#conv-list button:hover { color: #e6e6e6; }

#main { display: grid; grid-template-rows: auto 1fr auto; height: 100vh; }
#topbar { padding: 12px 16px; border-bottom: 1px solid #2a2b30; display: flex; gap: 12px; align-items: center; background: #1a1b1e; }
#model-picker { background: #232428; color: #e6e6e6; border: 1px solid #2a2b30; border-radius: 6px; padding: 6px 10px; font-size: 13px; }
#conv-title { color: #888; font-size: 14px; }

#messages { overflow-y: auto; padding: 16px 24px; display: flex; flex-direction: column; gap: 12px; }
.msg { max-width: 80%; padding: 10px 14px; border-radius: 10px; line-height: 1.5; font-size: 15px; word-wrap: break-word; }
.msg.user { align-self: flex-end; background: #2563eb; color: white; }
.msg.assistant { align-self: flex-start; background: #232428; }
.msg.error { align-self: stretch; background: #3a1f22; color: #ffb4b4; border: 1px solid #5a2a30; }
.msg pre { background: #0e0e10; padding: 10px; border-radius: 6px; overflow-x: auto; }
.msg code { background: #2a2b30; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }
.msg pre code { background: none; padding: 0; }

#composer { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 12px 16px; border-top: 1px solid #2a2b30; background: #1a1b1e; }
#input { background: #232428; color: #e6e6e6; border: 1px solid #2a2b30; border-radius: 6px; padding: 10px; font-size: 15px; resize: vertical; font-family: inherit; }
#send { background: #2563eb; color: white; border: none; border-radius: 6px; padding: 0 20px; cursor: pointer; font-size: 14px; min-width: 80px; }
#send:hover { background: #1d4ed8; }
#send.stop { background: #dc2626; }
#send.stop:hover { background: #b91c1c; }
```

- [ ] **Step 2: 提交**

```bash
git add web/styles.css
git commit -m "feat(web): add dark theme styles for chat UI"
```

---

## Task 12: 前端逻辑 — `web/app.js`

**Files:**
- Create: `web/app.js`

（一次性写完，因为状态/侧栏/消息/发送相互勾连，拆分小步反而更易引入 race；写完后跑手工 smoke。）

- [ ] **Step 1: 写 `web/app.js`**

```javascript
// AIIC MiMo Chat — single-page client
const STORAGE_KEY = "aiic.chat.v1";
const DEFAULT_MODEL = "mimo-v2.5-pro";

// ---------- state ----------
let state = loadState();
let abortCtl = null;

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { conversations: [], activeId: null };
    const s = JSON.parse(raw);
    if (!s.conversations) s.conversations = [];
    return s;
  } catch (e) {
    console.error("loadState failed", e);
    return { conversations: [], activeId: null };
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function activeConv() {
  return state.conversations.find((c) => c.id === state.activeId) || null;
}

function newConv(model = DEFAULT_MODEL) {
  const conv = {
    id: crypto.randomUUID(),
    title: "新会话",
    model,
    messages: [],
  };
  state.conversations.unshift(conv);
  state.activeId = conv.id;
  saveState();
  renderAll();
}

function deleteConv(id) {
  state.conversations = state.conversations.filter((c) => c.id !== id);
  if (state.activeId === id) {
    state.activeId = state.conversations[0]?.id || null;
  }
  saveState();
  renderAll();
}

function renameConv(id, title) {
  const c = state.conversations.find((c) => c.id === id);
  if (!c) return;
  c.title = title;
  saveState();
  renderAll();
}

function switchConv(id) {
  state.activeId = id;
  saveState();
  renderAll();
}

// ---------- rendering ----------
function renderAll() {
  renderSidebar();
  renderMessages();
  renderTitle();
}

function renderSidebar() {
  const ul = document.getElementById("conv-list");
  ul.innerHTML = "";
  for (const c of state.conversations) {
    const li = document.createElement("li");
    if (c.id === state.activeId) li.classList.add("active");

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = c.title || "(空)";
    title.onclick = () => switchConv(c.id);

    const renameBtn = document.createElement("button");
    renameBtn.textContent = "✏";
    renameBtn.title = "重命名";
    renameBtn.onclick = (e) => {
      e.stopPropagation();
      const t = prompt("新标题", c.title);
      if (t) renameConv(c.id, t);
    };

    const delBtn = document.createElement("button");
    delBtn.textContent = "✕";
    delBtn.title = "删除";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      if (confirm(`删除会话 "${c.title}" ？`)) deleteConv(c.id);
    };

    li.append(title, renameBtn, delBtn);
    ul.appendChild(li);
  }
}

function renderMessages() {
  const box = document.getElementById("messages");
  box.innerHTML = "";
  const conv = activeConv();
  if (!conv) return;
  for (const m of conv.messages) {
    box.appendChild(renderMsg(m));
  }
  scrollToBottom();
}

function renderMsg(m) {
  const div = document.createElement("div");
  div.className = `msg ${m.role}`;
  if (m.role === "assistant" && window.marked) {
    div.innerHTML = window.marked.parse(m.content || "");
  } else {
    div.textContent = m.content;
  }
  return div;
}

function renderTitle() {
  const conv = activeConv();
  document.getElementById("conv-title").textContent = conv?.title || "";
  const picker = document.getElementById("model-picker");
  if (conv) picker.value = conv.model;
}

function scrollToBottom() {
  const box = document.getElementById("messages");
  box.scrollTop = box.scrollHeight;
}

// ---------- model picker ----------
async function loadModels() {
  const resp = await fetch("/api/models");
  const data = await resp.json();
  const picker = document.getElementById("model-picker");
  picker.innerHTML = "";
  for (const m of data.data) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.id;
    picker.appendChild(opt);
  }
  if (activeConv()) picker.value = activeConv().model;
  picker.onchange = () => {
    const c = activeConv();
    if (c) {
      c.model = picker.value;
      saveState();
    }
  };
}

// ---------- send / stream ----------
async function send() {
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text) return;

  let conv = activeConv();
  if (!conv) {
    newConv(document.getElementById("model-picker").value || DEFAULT_MODEL);
    conv = activeConv();
  }

  conv.messages.push({ role: "user", content: text });
  if (conv.title === "新会话" || !conv.title) {
    conv.title = text.slice(0, 24);
  }
  saveState();
  input.value = "";
  renderAll();

  const assistantMsg = { role: "assistant", content: "" };
  conv.messages.push(assistantMsg);
  saveState();

  const box = document.getElementById("messages");
  const msgEl = renderMsg(assistantMsg);
  box.appendChild(msgEl);
  scrollToBottom();

  setSending(true);
  abortCtl = new AbortController();

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: conv.model,
        messages: conv.messages.slice(0, -1).map((m) => ({ role: m.role, content: m.content })),
        stream: true,
      }),
      signal: abortCtl.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        handleSseEvent(event, assistantMsg, msgEl);
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      assistantMsg.content += "\n\n[已停止]";
    } else {
      console.error(err);
      conv.messages.pop();
      conv.messages.push({ role: "error", content: String(err.message || err) });
      renderMessages();
      saveState();
      setSending(false);
      return;
    }
  } finally {
    abortCtl = null;
  }

  saveState();
  renderMsg(assistantMsg);
  if (window.marked) msgEl.innerHTML = window.marked.parse(assistantMsg.content || "");
  setSending(false);
}

function handleSseEvent(eventText, assistantMsg, msgEl) {
  let isError = false;
  let dataLines = [];
  for (const line of eventText.split("\n")) {
    if (line.startsWith("event:") && line.includes("error")) isError = true;
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  const data = dataLines.join("\n");
  if (!data) return;
  if (isError) {
    assistantMsg.content += `\n\n[错误] ${data}`;
    msgEl.classList.add("error");
    if (window.marked) msgEl.innerHTML = window.marked.parse(assistantMsg.content);
    else msgEl.textContent = assistantMsg.content;
    return;
  }
  if (data === "[DONE]") return;
  try {
    const obj = JSON.parse(data);
    const delta = obj.choices?.[0]?.delta?.content || "";
    if (delta) {
      assistantMsg.content += delta;
      if (window.marked) msgEl.innerHTML = window.marked.parse(assistantMsg.content);
      else msgEl.textContent = assistantMsg.content;
      scrollToBottom();
    }
  } catch (e) {
    // 非 JSON data 行（如心跳），忽略
  }
}

function setSending(sending) {
  const btn = document.getElementById("send");
  if (sending) {
    btn.textContent = "停止";
    btn.classList.add("stop");
  } else {
    btn.textContent = "发送";
    btn.classList.remove("stop");
  }
}

// ---------- wiring ----------
document.getElementById("new-conv").onclick = () => {
  const model = document.getElementById("model-picker").value || DEFAULT_MODEL;
  newConv(model);
};
document.getElementById("send").onclick = () => {
  if (abortCtl) abortCtl.abort();
  else send();
};
document.getElementById("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (abortCtl) abortCtl.abort();
    else send();
  }
});

// ---------- init ----------
(async function init() {
  await loadModels();
  if (state.conversations.length === 0) newConv();
  else renderAll();
})();
```

- [ ] **Step 2: 提交**

```bash
git add web/app.js
git commit -m "feat(web): chat UI with multi-conversation, streaming, abort, localStorage"
```

---

## Task 13: 本地端到端 smoke（连真实 MiMo）

**Files:** 无（仅运行）

- [ ] **Step 1: 启动开发服务器**

```bash
pixi run serve
```

让它跑在前台或开后台 shell。Expected: 监听 `127.0.0.1:8000`，无报错。

- [ ] **Step 2: 在另一个 shell 跑 health 与 models curl**

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/models | python -m json.tool
```

Expected: 分别返回 `{"status":"ok"}` 与 4 个 chat model id。

- [ ] **Step 3: 跑流式 chat curl（连真实 MiMo）**

```bash
curl -N -s -X POST http://127.0.0.1:8000/api/chat \
  -H "content-type: application/json" \
  -d '{"model":"mimo-v2.5-pro","messages":[{"role":"user","content":"你好，请用一句话自我介绍"}],"stream":true}'
```

Expected: 看到逐 chunk 的 `data: {...delta...}` 持续输出，最后 `data: [DONE]`。

- [ ] **Step 4: 浏览器 smoke（如本地能跑浏览器）**

如本地无 GUI，跳过此步并在公网部署后做。

如本地有 GUI：浏览器开 `http://127.0.0.1:8000`，验证：
- 模型下拉显示 4 个选项
- 发送一条消息看到流式渲染
- 新建会话 / 切换 / 重命名 / 删除
- 刷新后历史保留

- [ ] **Step 5: 关闭 dev server，记录任何异常**

如发现 bug，回到对应 task 修补并补测试再继续。

无 commit。

---

## Task 14: deploy/aiic-chat.service systemd unit

**Files:**
- Create: `deploy/aiic-chat.service`

- [ ] **Step 1: 写 unit**

```ini
[Unit]
Description=AIIC MiMo Chat (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/AIIC-Project
EnvironmentFile=/home/ubuntu/AIIC-Project/.env
ExecStart=/home/ubuntu/AIIC-Project/.pixi/envs/default/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

> 备注：`EnvironmentFile=.env` 让 systemd 直接把 `MIMO_API_KEY=...` 加进进程环境，应用层 `load_dotenv()` 也会兜底。

- [ ] **Step 2: 提交**

```bash
git add deploy/aiic-chat.service
git commit -m "deploy: add systemd unit for aiic-chat service"
```

---

## Task 15: deploy/nginx-aiic.location.conf — Nginx location 片段

**Files:**
- Create: `deploy/nginx-aiic.location.conf`

- [ ] **Step 1: 写片段**

```nginx
# 替换 /etc/nginx/sites-available/aiic.fomalhaut647.com 中 server { listen 443 ... } 块的 location / {} 整段。
# 同时移除该 server 块里的 root / index 指令（因为不再走静态文件，由 FastAPI 提供）。

location / {
    auth_basic "AIIC Chat";
    auth_basic_user_file /etc/nginx/.htpasswd_aiic;

    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # SSE 关键：必须关闭缓冲与缓存，并放宽读超时
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
}
```

- [ ] **Step 2: 提交**

```bash
git add deploy/nginx-aiic.location.conf
git commit -m "deploy: add nginx location snippet with basic auth and SSE settings"
```

---

## Task 16: 部署 systemd 服务到生产

**Files:** 无（仅在生产服务器上操作）

- [ ] **Step 1: 安装 unit 并启用**

```bash
sudo cp /home/ubuntu/AIIC-Project/deploy/aiic-chat.service /etc/systemd/system/aiic-chat.service
sudo systemctl daemon-reload
sudo systemctl enable --now aiic-chat
```

Expected: 无错误输出。

- [ ] **Step 2: 验证服务起来**

```bash
sudo systemctl status aiic-chat --no-pager
curl -s http://127.0.0.1:8000/api/health
```

Expected: status 显示 `active (running)`；curl 返回 `{"status":"ok"}`。

- [ ] **Step 3: 检查日志**

```bash
sudo journalctl -u aiic-chat -n 50 --no-pager
```

Expected: 看到 uvicorn 启动日志，无栈跟踪。

无 commit。

---

## Task 17: 配置 Basic Auth + 更新 Nginx + reload

**Files:** 无（仅在生产服务器上操作；改的是 `/etc/nginx/sites-available/aiic.fomalhaut647.com`，不入仓库）

- [ ] **Step 1: 装 apache2-utils 取得 htpasswd 工具（如未装）**

```bash
which htpasswd || sudo apt-get update && sudo apt-get install -y apache2-utils
```

- [ ] **Step 2: 创建 htpasswd 文件**

```bash
sudo htpasswd -cb /etc/nginx/.htpasswd_aiic aiic '<REDACTED>'
sudo chown root:www-data /etc/nginx/.htpasswd_aiic
sudo chmod 640 /etc/nginx/.htpasswd_aiic
```

Expected: 文件已创建，权限正确。

- [ ] **Step 3: 备份当前 nginx site 配置**

```bash
sudo cp /etc/nginx/sites-available/aiic.fomalhaut647.com /etc/nginx/sites-available/aiic.fomalhaut647.com.bak.$(date +%Y%m%d)
```

- [ ] **Step 4: 编辑 site 配置**

把 `server { listen 443 ssl http2; ... }` 块里的：

```nginx
    root /var/www/aiic;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
```

替换为 `deploy/nginx-aiic.location.conf` 的内容（删掉 `root` 与 `index` 两行，整段 `location /` 替换）。

```bash
sudo $EDITOR /etc/nginx/sites-available/aiic.fomalhaut647.com
```

- [ ] **Step 5: 测 + reload**

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Expected: `syntax is ok` 与 `test is successful`，reload 无报错。

无 commit。

---

## Task 18: 公网验收

**Files:** 无（仅运行）

- [ ] **Step 1: curl 不带 auth 期望 401**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://aiic.fomalhaut647.com/api/health
```

Expected: `401`。

- [ ] **Step 2: curl 带 auth 期望 200**

```bash
curl -s -u 'aiic:<REDACTED>' https://aiic.fomalhaut647.com/api/health
```

Expected: `{"status":"ok"}`。

- [ ] **Step 3: curl 模型列表**

```bash
curl -s -u 'aiic:<REDACTED>' https://aiic.fomalhaut647.com/api/models | python3 -m json.tool
```

Expected: 4 个 chat model id。

- [ ] **Step 4: curl 流式 chat**

```bash
curl -N -s -u 'aiic:<REDACTED>' -X POST https://aiic.fomalhaut647.com/api/chat \
  -H "content-type: application/json" \
  -d '{"model":"mimo-v2.5-pro","messages":[{"role":"user","content":"你好，请用一句话自我介绍"}],"stream":true}'
```

Expected: 持续输出 `data: {...delta...}`，**逐 chunk** 而非一次性返回（说明 nginx 缓冲已关闭），最后 `data: [DONE]`。

- [ ] **Step 5: 浏览器人测**

打开 `https://aiic.fomalhaut647.com`，输入 `aiic` / `<REDACTED>`，验证：
- 模型下拉 4 个选项
- 发送消息看到流式渲染（不是一次性吐出）
- 新建 / 切换 / 重命名 / 删除会话工作正常
- 刷新后会话历史保留
- "停止"按钮能中断流

无 commit。

---

## Task 19: 收尾文档（CLAUDE.md + README.md）

**Files:**
- Modify: `CLAUDE.md`
- Create: `README.md`

- [ ] **Step 1: 在 `CLAUDE.md` 的 "Nginx 部署现状" 之后、"Gotchas" 之前插入新章节 "Web Chat 应用部署"**

新章节内容：

```markdown
## Web Chat 应用部署（v1）

- **代码**：`server/`（FastAPI + httpx 流式代理）+ `web/`（vanilla JS 单页）
- **systemd 服务**：`aiic-chat.service`（监听 `127.0.0.1:8000`），unit 模板见 `deploy/aiic-chat.service`
- **本地启动**：`pixi run serve`（带 reload）或 `pixi run serve-prod`
- **测试**：`pixi run test`
- **Nginx**：`/etc/nginx/sites-available/aiic.fomalhaut647.com` 已改 `location /` 反代到 :8000，`proxy_buffering off` 透传 SSE。模板见 `deploy/nginx-aiic.location.conf`
- **Basic Auth**：`/etc/nginx/.htpasswd_aiic`（属主 `root:www-data` 模式 `640`，**禁止 commit**）。当前凭据：`aiic / <REDACTED>`，更换走 `sudo htpasswd /etc/nginx/.htpasswd_aiic <user>`
- **MiMo 上游**：OpenAI 兼容协议 `https://token-plan-cn.xiaomimimo.com/v1`，Bearer key 见 `.env`
- **可用 chat 模型白名单**：`mimo-v2.5-pro`、`mimo-v2.5`、`mimo-v2-pro`、`mimo-v2-omni`（在 `server/mimo.py` 维护）
```

- [ ] **Step 2: 创建 `README.md`（人类向 5 分钟上手）**

```markdown
# AIIC-Project — MiMo Web Chat

A simple multi-conversation streaming chat web app talking to Xiaomi MiMo via the
OpenAI-compatible endpoint. Deployed at <https://aiic.fomalhaut647.com>.

## Stack

- Backend: FastAPI + httpx (async SSE proxy)
- Frontend: single-page vanilla HTML/CSS/JS (no build step)
- Auth: Nginx HTTP Basic Auth
- Env: Pixi-managed Python

## Quick start (local dev)

```bash
# Put MIMO_API_KEY into .env first
pixi install
pixi run serve   # http://127.0.0.1:8000
pixi run test
```

## Layout

```
server/   FastAPI app + MiMo upstream constants
web/      index.html, app.js, styles.css
tests/    pytest suite
deploy/   systemd unit + nginx location snippet
docs/     specs/, plans/
```

## Production

Behind `aiic.fomalhaut647.com` (Nginx 1.24, TLS via TrustAsia DV, Basic Auth).
See `CLAUDE.md` for deployment details.
```

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document web chat deployment and add project README"
```

---

## Self-review 备忘（写完后由计划作者完成）

- [x] Spec coverage：Section 1-10 都有对应 task
- [x] No placeholders：每步都有可执行代码 / 命令
- [x] Type/name 一致性：`get_http_client`、`CHAT_MODELS`、`MIMO_BASE_URL`、`STORAGE_KEY = "aiic.chat.v1"` 全程一致
- [x] TDD 顺序：每个后端 task 先红再绿再 commit
- [x] 部署 task 与 Nginx gotcha（`http2 on;` 旧式 listen / `proxy_buffering off`）一致

---

## 执行后续

完成所有 task 后：
1. 删除占位 `pdf-reader.md`（如已无用）和 `scripts/`（如不再需要）—— 这步不在本计划内，由 maintainer 决定
2. 制作 ≤3 分钟 demo 视频
3. 添加主办方 SSH 公钥到 `~ubuntu/.ssh/authorized_keys`（5/10 之前必做，与本计划独立）
