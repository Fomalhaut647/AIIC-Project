"""SessionStore Plan2 user profile tests — Spec D §4.2."""
import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from services.schemas import SessionMeta, Target, UserProfile
from services.store import SessionStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> SessionStore:
    """SessionStore rooted at tmp_path, sessions/ + users/ subdirs auto-created."""
    return SessionStore(data_dir=tmp_path)


def _meta(sid: str, score: int = 70, weaknesses: list[str] | None = None) -> SessionMeta:
    return SessionMeta(
        session_id=sid,
        created_at=datetime(2026, 5, 12),
        target=Target.BAOYAN,
        project_summary_short="P1",
        overall_score=score,
        weakness_tags=weaknesses or [],
    )


def test_load_user_profile_empty_returns_default(tmp_store: SessionStore):
    """不存在的 user_id 返回空 UserProfile（不 raise）。"""
    profile = tmp_store.load_user_profile("ghost")
    assert profile.user_id == "ghost"
    assert profile.total_sessions == 0
    assert profile.sessions == []


def test_update_user_profile_persists_to_disk(tmp_store: SessionStore, tmp_path: Path):
    """update → 文件落盘 → 再 load 读回内容一致。"""
    asyncio.run(tmp_store.update_user_profile("user-A", _meta("s1", 80, ["baseline"])))

    file = tmp_path / "users" / "user-A.json"
    assert file.exists()

    loaded = tmp_store.load_user_profile("user-A")
    assert loaded.total_sessions == 1
    assert loaded.average_score == 80.0
    assert loaded.recurring_weaknesses == {"baseline": 1}


def test_update_user_profile_aggregates_multiple(tmp_store: SessionStore):
    """两次 update → sessions=2 + average 重算 + weakness count 累加。"""
    asyncio.run(tmp_store.update_user_profile("user-B", _meta("s1", 60, ["baseline"])))
    asyncio.run(tmp_store.update_user_profile("user-B", _meta("s2", 80, ["个人贡献"])))

    profile = tmp_store.load_user_profile("user-B")
    assert profile.total_sessions == 2
    assert profile.average_score == 70.0
    assert profile.recurring_weaknesses == {"baseline": 1, "个人贡献": 1}


def test_update_user_profile_atomic_write(tmp_store: SessionStore, tmp_path: Path):
    """原子写：写过程不应留下半截文件（用 .tmp + rename）。
    断言 final 文件存在 + 内容是合法 JSON。"""
    asyncio.run(tmp_store.update_user_profile("user-C", _meta("s1")))

    file = tmp_path / "users" / "user-C.json"
    payload = json.loads(file.read_text())
    assert "user_id" in payload
    assert payload["user_id"] == "user-C"


def test_list_user_sessions_returns_metas(tmp_store: SessionStore):
    """list_user_sessions 返回 user 的 SessionMeta[]。"""
    asyncio.run(tmp_store.update_user_profile("user-D", _meta("s1", 70)))
    asyncio.run(tmp_store.update_user_profile("user-D", _meta("s2", 80)))

    metas = tmp_store.list_user_sessions("user-D")
    assert len(metas) == 2
    assert {m.session_id for m in metas} == {"s1", "s2"}


def test_update_user_profile_concurrent_writes_no_lost_updates(tmp_store: SessionStore):
    """证明 per-user asyncio.Lock 真的在序列化 RMW：N 个并发 update 后必须有 N 条 sessions。

    没有 lock 时（多个 coroutine 各自 read-then-write），后写覆盖前写 → total < N。
    有 lock → total == N。
    """

    async def fan_out():
        await asyncio.gather(*[
            tmp_store.update_user_profile("user-E", _meta(f"s{i}", 70))
            for i in range(10)
        ])

    asyncio.run(fan_out())

    profile = tmp_store.load_user_profile("user-E")
    assert profile.total_sessions == 10
    assert {m.session_id for m in profile.sessions} == {f"s{i}" for i in range(10)}
