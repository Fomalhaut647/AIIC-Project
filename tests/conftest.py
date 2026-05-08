import os
import pytest
from fastapi.testclient import TestClient

# 让导入 server.main 时能找到 MIMO_API_KEY
os.environ.setdefault("MIMO_API_KEY", "test-key")

from server.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
