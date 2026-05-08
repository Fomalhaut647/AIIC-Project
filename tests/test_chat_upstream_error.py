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
