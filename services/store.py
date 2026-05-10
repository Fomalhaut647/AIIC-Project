"""In-memory session store with fire-and-forget JSON dump."""
import asyncio
import json
from datetime import datetime
from pathlib import Path
import uuid

from services.schemas import (
    InterviewPacket, InterviewSession, InterviewTurn, SessionMeta, UserModel,
    UserProfile,
)


class SessionNotFound(KeyError):
    pass


class SessionStore:
    def __init__(
        self,
        dump_dir: Path | None = None,      # legacy alias: directly the sessions dir
        data_dir: Path | None = None,      # new: data root; sessions/ + users/ derived
    ):
        if data_dir is not None:
            self.data_dir = Path(data_dir)
            self._dump_dir = self.data_dir / "sessions"
        elif dump_dir is not None:
            self._dump_dir = Path(dump_dir)
            # backward compat: derive data_dir as parent so users/ sits beside sessions/
            self.data_dir = self._dump_dir.parent
        else:
            self.data_dir = Path("data")
            self._dump_dir = self.data_dir / "sessions"
        self._sessions: dict[str, InterviewSession] = {}
        self._dump_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "users").mkdir(parents=True, exist_ok=True)
        self._user_locks: dict[str, asyncio.Lock] = {}

    def create(self, packet: InterviewPacket, user_model: UserModel) -> str:
        sid = uuid.uuid4().hex
        self._sessions[sid] = InterviewSession(
            session_id=sid, user_model=user_model, packet=packet,
        )
        return sid

    def get(self, session_id: str) -> InterviewSession:
        if session_id not in self._sessions:
            raise SessionNotFound(session_id)
        return self._sessions[session_id]

    def append_turn(self, session_id: str, turn: InterviewTurn) -> None:
        session = self.get(session_id)
        session.turns.append(turn)
        self._dump(session)

    def _dump(self, session: InterviewSession) -> None:
        path = self._dump_dir / f"{session.session_id}.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    # ----------------- Plan2 长期训练 (Spec D §4.2) -----------------

    def _user_profile_path(self, user_id: str) -> Path:
        return self.data_dir / "users" / f"{user_id}.json"

    def load_user_profile(self, user_id: str) -> UserProfile:
        """读 data/users/<user_id>.json; 不存在返回空 UserProfile."""
        path = self._user_profile_path(user_id)
        if not path.exists():
            return UserProfile(user_id=user_id, created_at=datetime.now())
        payload = json.loads(path.read_text(encoding="utf-8"))
        return UserProfile.model_validate(payload)

    def list_user_sessions(self, user_id: str) -> list[SessionMeta]:
        return self.load_user_profile(user_id).sessions

    async def update_user_profile(self, user_id: str, meta: SessionMeta) -> None:
        """聚合一条 SessionMeta 到 user profile, 原子写盘.

        Trade-off: read/write inside the lock are sync (blocking) calls. Acceptable at
        the expected write rate (~1 per session review). The async signature reserves
        room to off-load to a thread pool later if profiles balloon.
        Per-user `asyncio.Lock` serializes RMW so concurrent updates to the same user
        cannot lose entries. The shared `.tmp` filename is also per-user-safe via
        the same lock — different users write disjoint paths and never contend.
        """
        lock = self._user_locks.setdefault(user_id, asyncio.Lock())

        async with lock:
            profile = self.load_user_profile(user_id)
            profile.add_session_meta(meta)

            path = self._user_profile_path(user_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(path)  # atomic rename
