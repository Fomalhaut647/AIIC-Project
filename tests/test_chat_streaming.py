import json

import httpx


SSE_BODY = (
    b"data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"hello \"}}]}\n\n"
    b"data: {\"id\":\"1\",\"choices\":[{\"delta\":{\"content\":\"world\"}}]}\n\n"
    b"data: [DONE]\n\n"
)


class _SSEStream(httpx.AsyncByteStream):
    """Wraps static bytes as an AsyncByteStream for mock responses.

    httpx.Response(content=...) eagerly calls self.read() in __init__,
    marking is_stream_consumed=True before aiter_raw() can be called.
    Using stream= bypasses that path and keeps the response streamable.
    """

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self):
        yield self._data


def test_streaming_passes_upstream_chunks_through(mock_upstream):
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("authorization")
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            stream=_SSEStream(SSE_BODY),
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
