from functools import lru_cache

from ..config import DATA_DIR, get_settings
from .base import SessionRepository
from .firestore_store import FirestoreSessionRepository
from .json_store import JsonSessionRepository


@lru_cache
def get_repository() -> SessionRepository:
    settings = get_settings()
    if settings.data_backend == "firestore":
        project = settings.firebase_project_id or settings.google_cloud_project
        return FirestoreSessionRepository(project)
    return JsonSessionRepository(DATA_DIR / "sessions")

