"""Test the /api/healthz endpoint.

This is the contract the 主办方 will hit after SSH-ing into the server to
verify the deploy is live (see Spec C §2.1). The shape MUST match docs.
"""
from fastapi.testclient import TestClient

from server.main import app


def test_healthz_returns_ok():
    with TestClient(app) as client:
        resp = client.get("/api/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["provider"] == "deepseek"
        assert body["version"] == "v2-mvp"
        assert "commit_hash" in body
        assert "deploy_time" in body


def test_healthz_commit_hash_nonempty():
    """commit_hash should be either a short SHA or 'unknown' (never empty)."""
    with TestClient(app) as client:
        body = client.get("/api/healthz").json()
        assert isinstance(body["commit_hash"], str)
        assert len(body["commit_hash"]) > 0
