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
