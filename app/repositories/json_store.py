import json
import os
import threading
from pathlib import Path

from ..models import StudySession, utc_now


class JsonSessionRepository:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, session_id: str) -> Path:
        if not session_id.isalnum():
            raise ValueError("Invalid session id")
        return self.directory / f"{session_id}.json"

    def create(self, session: StudySession) -> StudySession:
        with self._lock:
            path = self._path(session.id)
            if path.exists():
                raise ValueError("Session already exists")
            return self.save(session)

    def get(self, session_id: str) -> StudySession | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        with self._lock, path.open("r", encoding="utf-8") as stream:
            return StudySession.model_validate(json.load(stream))

    def save(self, session: StudySession) -> StudySession:
        with self._lock:
            session.updated_at = utc_now()
            session.state_version += 1
            path = self._path(session.id)
            temp_path = path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as stream:
                json.dump(session.model_dump(mode="json"), stream, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
            return session

    def list(self) -> list[StudySession]:
        sessions: list[StudySession] = []
        for path in self.directory.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as stream:
                    sessions.append(StudySession.model_validate(json.load(stream)))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

