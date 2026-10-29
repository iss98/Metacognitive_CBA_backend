from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app, repo_dependency
from app.repositories.json_store import JsonSessionRepository


def test_complete_demo_flow():
    test_directory = Path(__file__).resolve().parents[1] / ".test-data" / uuid4().hex
    repository = JsonSessionRepository(test_directory)
    app.dependency_overrides[repo_dependency] = lambda: repository
    client = TestClient(app)

    created = client.post("/api/sessions", json={"participant_code": "P-TEST"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    items = client.get("/api/survey-items").json()
    survey = client.put(
        f"/api/sessions/{session_id}/survey",
        json={"responses": [{"item_id": item["id"], "score": 3} for item in items]},
    )
    assert survey.json()["state"] == "survey_done"

    assert client.post(f"/api/sessions/{session_id}/recording/start").json()["state"] == "recording"
    transcript = client.post(
        f"/api/sessions/{session_id}/transcript-turns",
        json={
            "segments": [
                {
                    "id": "seg_test",
                    "text": "먼저 조건을 확인하고 이항정리를 써 보자. 계산 뒤 다시 확인했다.",
                    "source": "manual",
                }
            ]
        },
    )
    assert transcript.status_code == 200
    assert client.post(f"/api/sessions/{session_id}/recording/complete").json()["state"] == "transcript_ready"

    prepared = client.post(f"/api/sessions/{session_id}/prepare-interview")
    assert prepared.status_code == 200
    assert len(prepared.json()["questions"]) == 17
    current = client.post(f"/api/sessions/{session_id}/interview/start").json()

    while current["state"] == "interviewing":
        question = current["questions"][current["current_question_index"]]
        current = client.post(
            f"/api/sessions/{session_id}/interview/answers",
            json={
                "question_id": question["id"],
                "text": "그때 문제 조건을 먼저 확인했습니다. 계산 결과가 조건에 맞는지 다시 보았기 때문입니다.",
            },
        ).json()

    assert current["state"] == "interview_done"
    rated = client.post(f"/api/sessions/{session_id}/rate")
    assert rated.status_code == 200
    payload = rated.json()
    assert payload["state"] == "results_ready"
    assert len(payload["item_ratings"]) == 17
    assert len(payload["factor_ratings"]) == 7

    app.dependency_overrides.clear()
    for path in test_directory.glob("*.json"):
        path.unlink()
    test_directory.rmdir()

