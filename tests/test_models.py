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
