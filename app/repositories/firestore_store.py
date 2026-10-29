from google.cloud import firestore

from ..models import StudySession


class FirestoreSessionRepository:
    """Production repository. Nested artifacts stay embedded in the MVP document.

    Before a large pilot, move transcript segments and interview turns to subcollections
    to stay comfortably below Firestore document limits.
    """

    def __init__(self, project: str):
        self.client = firestore.Client(project=project or None)
        self.collection = self.client.collection("sessions")

    def create(self, session: StudySession) -> StudySession:
        self.collection.document(session.id).create(session.model_dump(mode="json"))
        return session

    def get(self, session_id: str) -> StudySession | None:
        snapshot = self.collection.document(session_id).get()
        return StudySession.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def save(self, session: StudySession) -> StudySession:
        from ..models import utc_now

        session.updated_at = utc_now()
        session.state_version += 1
        self.collection.document(session.id).set(session.model_dump(mode="json"))
        return session

    def list(self) -> list[StudySession]:
        query = self.collection.order_by("updated_at", direction=firestore.Query.DESCENDING).limit(100)
        return [StudySession.model_validate(item.to_dict()) for item in query.stream()]

