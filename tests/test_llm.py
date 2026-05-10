import json
import httpx
import pytest
from unittest.mock import patch, AsyncMock
from pydantic import BaseModel

from services.llm import call_deepseek, LLMSchemaError


class _DummyOut(BaseModel):
    name: str
    score: int


def _mock_response(content: str):
    """Build a fake httpx-like response with .json() returning OpenAI-style body."""
    resp = AsyncMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"choices": [{"message": {"content": content}}]}
    return resp


@pytest.mark.asyncio
async def test_call_returns_text_when_no_schema():
    with patch("services.llm._post_chat", new=AsyncMock(return_value=_mock_response("hello"))):
        out = await call_deepseek([{"role": "user", "content": "hi"}])
        assert out == "hello"


@pytest.mark.asyncio
async def test_call_parses_valid_json_into_schema():
    with patch("services.llm._post_chat", new=AsyncMock(
        return_value=_mock_response('{"name": "x", "score": 10}'),
    )):
        out = await call_deepseek(
            [{"role": "user", "content": "ok"}],
            response_schema=_DummyOut,
        )
        assert isinstance(out, _DummyOut)
        assert out.name == "x"


@pytest.mark.asyncio
async def test_repair_retry_then_success():
    bad = "this is not json"
    good = '{"name": "x", "score": 10}'
    with patch("services.llm._post_chat", new=AsyncMock(
        side_effect=[_mock_response(bad), _mock_response(good)],
    )) as m:
        out = await call_deepseek(
            [{"role": "user", "content": "ok"}],
            response_schema=_DummyOut,
        )
        assert isinstance(out, _DummyOut)
        assert m.await_count == 2


@pytest.mark.asyncio
async def test_repair_fails_returns_fallback():
    bad = "still not json"
    fallback = _DummyOut(name="fb", score=0)
    with patch("services.llm._post_chat", new=AsyncMock(
        side_effect=[_mock_response(bad), _mock_response(bad)],
    )):
        out = await call_deepseek(
            [{"role": "user", "content": "ok"}],
            response_schema=_DummyOut,
            fallback=fallback,
        )
        assert out == fallback


@pytest.mark.asyncio
async def test_repair_fails_no_fallback_raises():
    bad = "still not json"
    with patch("services.llm._post_chat", new=AsyncMock(
        side_effect=[_mock_response(bad), _mock_response(bad)],
    )):
        with pytest.raises(LLMSchemaError):
            await call_deepseek(
                [{"role": "user", "content": "ok"}],
                response_schema=_DummyOut,
            )


# ===== Reviewer #2 fix: spec §7 网络超时 retry once + fallback =====

@pytest.mark.asyncio
async def test_network_timeout_retries_then_succeeds():
    """First call raises TimeoutException → sleep 5s → retry succeeds."""
    good = _mock_response("hello")
    side = [httpx.TimeoutException("read timeout"), good]
    with patch("services.llm._post_chat", new=AsyncMock(side_effect=side)) as m, \
         patch("services.llm.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        out = await call_deepseek([{"role": "user", "content": "hi"}])
        assert out == "hello"
        assert m.await_count == 2
        # 网络重试 sleep 必须是 5s
        sleep_mock.assert_awaited_once_with(5.0)


@pytest.mark.asyncio
async def test_network_double_failure_returns_fallback():
    """Both attempts time out → return fallback (text mode)."""
    side = [httpx.TimeoutException("t1"), httpx.ConnectError("t2")]
    with patch("services.llm._post_chat", new=AsyncMock(side_effect=side)), \
         patch("services.llm.asyncio.sleep", new=AsyncMock()):
        out = await call_deepseek(
            [{"role": "user", "content": "hi"}],
            fallback="DEGRADED",
        )
        assert out == "DEGRADED"


@pytest.mark.asyncio
async def test_network_double_failure_no_fallback_raises():
    """No fallback → propagate the network exception (caller sees it)."""
    side = [httpx.TimeoutException("t1"), httpx.TimeoutException("t2")]
    with patch("services.llm._post_chat", new=AsyncMock(side_effect=side)), \
         patch("services.llm.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(httpx.TimeoutException):
            await call_deepseek([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_network_timeout_with_schema_returns_fallback():
    """Schema-mode + double network failure + fallback provided → return fallback."""
    fallback = _DummyOut(name="fb", score=0)
    side = [httpx.TimeoutException("t1"), httpx.ConnectError("t2")]
    with patch("services.llm._post_chat", new=AsyncMock(side_effect=side)), \
         patch("services.llm.asyncio.sleep", new=AsyncMock()):
        out = await call_deepseek(
            [{"role": "user", "content": "hi"}],
            response_schema=_DummyOut,
            fallback=fallback,
        )
        assert out == fallback
