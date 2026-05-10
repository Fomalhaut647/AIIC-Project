import json
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
