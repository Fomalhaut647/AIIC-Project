import os
from typing import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MIMO_API_KEY", "test-key")

from server.main import app, get_http_client  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


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
