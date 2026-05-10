"""In-memory session store with fire-and-forget JSON dump."""
from pathlib import Path
import uuid

from services.schemas import (
    InterviewPacket, InterviewSession, InterviewTurn, UserModel,
)


class SessionNotFound(KeyError):
    pass


class SessionStore:
    def __init__(self, dump_dir: Path = Path("data/sessions")):
        self._sessions: dict[str, InterviewSession] = {}
        self._dump_dir = Path(dump_dir)
        self._dump_dir.mkdir(parents=True, exist_ok=True)

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
