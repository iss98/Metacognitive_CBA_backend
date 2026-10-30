from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .agents import prepare_interview_assets, rate_completed_interview
from .agents.demo import is_answer_sufficient, make_followup
from .agents.model import assess_answer_with_model
from .config import DATA_DIR, RESOURCE_DIR, Settings, get_settings
from .content import SURVEY_ITEMS
from .models import (
    AudioCheckResult,
    AudioCheckSubmission,
    ComparisonChoice,
    CreateSessionRequest,
    InterviewAnswer,
    InterviewTurn,
    SessionState,
    SessionSummary,
    StudySession,
    SurveySubmission,
    TranscriptSubmission,
    TranscriptSegment,
)
from .repositories import get_repository
from .repositories.base import SessionRepository
from .services.transcription import transcribe_recorded_audio


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
allowed_origins = list({settings.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"})
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def repo_dependency() -> SessionRepository:
    return get_repository()


def require_session(session_id: str, repo: SessionRepository) -> StudySession:
    session = repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="실험 세션을 찾을 수 없습니다.")
    return session


def require_state(session: StudySession, allowed: set[SessionState]) -> None:
    if session.state not in allowed:
        allowed_text = ", ".join(state.value for state in allowed)
        raise HTTPException(
            status_code=409,
            detail=f"현재 단계({session.state.value})에서는 이 작업을 할 수 없습니다. 허용 단계: {allowed_text}",
        )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": settings.llm_provider,
        "data_backend": settings.data_backend,
        "openai_realtime_configured": bool(settings.openai_api_key),
    }


@app.get(f"{settings.api_prefix}/config/public")
def public_config() -> dict:
    return {
        "demo_mode": settings.llm_provider == "mock",
        "realtime_available": bool(settings.openai_api_key),
        "max_followups": settings.max_followups_per_question,
        "rubric_version": settings.rubric_version,
    }


@app.get(f"{settings.api_prefix}/problem")
def problem() -> dict:
    path = RESOURCE_DIR / "round_table_problem_schema.json"
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    return {
        "id": payload["problem_id"],
        "title": payload["title"],
        "stem": payload["stem"],
        "stem_math": payload.get("stem_math", payload["stem"]),
        "image_path": "/images/round-table-assignment.png",
        "image_alt": "원탁에 둘러앉은 학생들에게 수를 배정한 예시",
    }


@app.get(f"{settings.api_prefix}/survey-items")
def survey_items() -> list:
    return SURVEY_ITEMS


@app.post(f"{settings.api_prefix}/sessions", response_model=StudySession)
def create_session(payload: CreateSessionRequest, repo: SessionRepository = Depends(repo_dependency)):
    survey_order = [item.id for item in SURVEY_ITEMS]
    random.SystemRandom().shuffle(survey_order)
    session = StudySession(
        participant_code=payload.participant_code.strip(),
        execution_mode="demo" if settings.llm_provider == "mock" else "model",
        survey_order=survey_order,
    )
    return repo.create(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/audio-check", response_model=StudySession)
def complete_audio_check(
    session_id: str,
    payload: AudioCheckSubmission,
    repo: SessionRepository = Depends(repo_dependency),
):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.AUDIO_CHECK, SessionState.CREATED})
    expected = "안녕하세요? 오늘 날씨가 참 좋습니다."

    def normalize(value: str) -> str:
        return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()

    session.audio_check = AudioCheckResult(
        expected_text=expected,
        transcript=payload.transcript.strip(),
        normalized_match=normalize(payload.transcript) == normalize(expected),
    )
    session.state = SessionState.CREATED
    return repo.save(session)


@app.get(f"{settings.api_prefix}/sessions", response_model=list[SessionSummary])
def list_sessions(repo: SessionRepository = Depends(repo_dependency)):
    return [
        SessionSummary(
            id=session.id,
            participant_code=session.participant_code,
            state=session.state,
            updated_at=session.updated_at,
            execution_mode=session.execution_mode,
        )
        for session in repo.list()
    ]


@app.get(f"{settings.api_prefix}/sessions/{{session_id}}", response_model=StudySession)
def get_session(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    return require_session(session_id, repo)


@app.put(f"{settings.api_prefix}/sessions/{{session_id}}/survey", response_model=StudySession)
def submit_survey(
    session_id: str,
    payload: SurveySubmission,
    repo: SessionRepository = Depends(repo_dependency),
):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.CREATED, SessionState.SURVEY_DONE})
    expected = {item.id for item in SURVEY_ITEMS}
    submitted = {item.item_id for item in payload.responses}
    if submitted != expected:
        missing = sorted(expected - submitted)
        extra = sorted(submitted - expected)
        raise HTTPException(status_code=422, detail={"missing": missing, "extra": extra})
    item_by_id = {item.id: item for item in SURVEY_ITEMS}
    order_by_id = {
        item_id: index
        for index, item_id in enumerate(session.survey_order or [item.id for item in SURVEY_ITEMS], start=1)
    }
    session.survey_responses = [
        response.model_copy(
            update={
                "factor": item_by_id[response.item_id].factor,
                "display_order": order_by_id[response.item_id],
            }
        )
        for response in payload.responses
    ]
    session.state = SessionState.SURVEY_DONE
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/recording/start", response_model=StudySession)
def start_recording(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.SURVEY_DONE, SessionState.RECORDING})
    session.state = SessionState.RECORDING
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/transcript-turns", response_model=StudySession)
def add_transcript(
    session_id: str,
    payload: TranscriptSubmission,
    repo: SessionRepository = Depends(repo_dependency),
):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.RECORDING, SessionState.TRANSCRIPT_READY})
    existing_ids = {segment.id for segment in session.transcript_segments}
    for segment in payload.segments:
        if segment.id not in existing_ids:
            segment.order = len(session.transcript_segments) + 1
            session.transcript_segments.append(segment)
            existing_ids.add(segment.id)
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/recording/complete", response_model=StudySession)
def complete_recording(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.RECORDING, SessionState.TRANSCRIPT_READY})
    if not session.transcript_segments:
        raise HTTPException(status_code=422, detail="전사 세그먼트가 한 개 이상 필요합니다.")
    session.state = SessionState.TRANSCRIPT_READY
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/transcription/recover", response_model=StudySession)
def recover_transcript(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.RECORDING, SessionState.TRANSCRIPT_READY})
    if not session.audio_path:
        raise HTTPException(status_code=422, detail="파일 전사에 사용할 원본 음성이 없습니다.")
    try:
        text = transcribe_recorded_audio(session.audio_path)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    session.transcript_segments.append(
        TranscriptSegment(
            order=len(session.transcript_segments) + 1,
            text=text,
            source="file_recovery",
        )
    )
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/audio", response_model=StudySession)
async def upload_audio(
    session_id: str,
    audio: UploadFile = File(...),
    repo: SessionRepository = Depends(repo_dependency),
):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.RECORDING, SessionState.TRANSCRIPT_READY})
    suffix = Path(audio.filename or "recording.webm").suffix.lower()
    if suffix not in {".webm", ".wav", ".mp3", ".m4a", ".ogg"}:
        suffix = ".webm"
    chunks: list[bytes] = []
    size = 0
    while chunk := await audio.read(1024 * 1024):
        size += len(chunk)
        if size > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="음성 파일은 100MB 이하여야 합니다.")
        chunks.append(chunk)
    content = b"".join(chunks)
    if settings.audio_bucket:
        from google.cloud import storage

        object_name = f"think-aloud/{session.id}/original{suffix}"
        bucket = storage.Client(project=settings.google_cloud_project or None).bucket(settings.audio_bucket)
        bucket.blob(object_name).upload_from_string(
            content,
            content_type=audio.content_type or "audio/webm",
        )
        session.audio_path = f"gs://{settings.audio_bucket}/{object_name}"
    else:
        target = DATA_DIR / "audio" / f"{session.id}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        session.audio_path = str(target)
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/transcription-token")
async def transcription_token(
    session_id: str,
    repo: SessionRepository = Depends(repo_dependency),
    app_settings: Settings = Depends(get_settings),
):
    session = require_session(session_id, repo)
    require_state(
        session,
        {SessionState.AUDIO_CHECK, SessionState.SURVEY_DONE, SessionState.RECORDING},
    )
    if not app_settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY가 설정되지 않아 데모 전사를 사용해야 합니다.")
    safety_id = hashlib.sha256(session.id.encode("utf-8")).hexdigest()
    transcription_prompt = (
        "한국어 음성 입력 확인 문장"
        if session.state == SessionState.AUDIO_CHECK
        else "한국어로 수학 문제를 풀며 생각을 소리 내어 말하는 녹음"
    )
    body = {
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "transcription": {
                        "model": app_settings.openai_realtime_transcribe_model,
                        "prompt": transcription_prompt,
                        "keywords": ["원탁", "이항정리", "조합", "실수", "허수", "전이행렬"],
                        "languages": ["ko"],
                        "delay": "low",
                    },
                    "turn_detection": None,
                }
            },
        }
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {app_settings.openai_api_key}",
                "Content-Type": "application/json",
                "OpenAI-Safety-Identifier": safety_id,
            },
            json=body,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenAI 전사 세션 생성 실패: {response.text}")
    return response.json()


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/prepare-interview", response_model=StudySession)
def prepare_interview(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    session = require_session(session_id, repo)
    require_state(
        session,
        {SessionState.TRANSCRIPT_READY, SessionState.SCHEMA_READY, SessionState.QUESTIONS_READY},
    )
    schema, questions = prepare_interview_assets(session)
    session.student_schema = schema
    session.questions = questions
    session.state = SessionState.QUESTIONS_READY
    session.current_question_index = 0
    if questions:
        questions[0].status = "active"
        session.interview_turns = [
            InterviewTurn(
                question_id=questions[0].id,
                role="assistant",
                text=questions[0].text,
                kind="base_question",
            )
        ]
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/interview/start", response_model=StudySession)
def start_interview(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.QUESTIONS_READY, SessionState.INTERVIEWING})
    session.state = SessionState.INTERVIEWING
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/interview/answers", response_model=StudySession)
def submit_interview_answer(
    session_id: str,
    payload: InterviewAnswer,
    repo: SessionRepository = Depends(repo_dependency),
):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.INTERVIEWING})
    if session.current_question_index >= len(session.questions):
        raise HTTPException(status_code=409, detail="모든 기본 질문이 완료되었습니다.")
    question = session.questions[session.current_question_index]
    if payload.question_id != question.id:
        raise HTTPException(status_code=409, detail="현재 진행 중인 질문과 일치하지 않습니다.")
    session.interview_turns.append(
        InterviewTurn(question_id=question.id, role="student", text=payload.text.strip(), kind="answer")
    )
    student_answers = [
        turn.text
        for turn in session.interview_turns
        if turn.question_id == question.id and turn.role == "student"
    ]
    if settings.llm_provider == "mock":
        sufficient = is_answer_sufficient(" ".join(student_answers))
        followup_text = make_followup(question)
    else:
        decision = assess_answer_with_model(question, student_answers)
        sufficient = decision.sufficient
        followup_text = decision.followup or make_followup(question)
    if not sufficient and question.followup_count < settings.max_followups_per_question:
        question.followup_count += 1
        session.interview_turns.append(
            InterviewTurn(
                question_id=question.id,
                role="assistant",
                text=followup_text,
                kind="followup",
            )
        )
        return repo.save(session)

    question.status = "answered"
    session.current_question_index += 1
    if session.current_question_index >= len(session.questions):
        session.state = SessionState.INTERVIEW_DONE
        return repo.save(session)

    next_question = session.questions[session.current_question_index]
    next_question.status = "active"
    session.interview_turns.append(
        InterviewTurn(
            question_id=next_question.id,
            role="assistant",
            text=next_question.text,
            kind="base_question",
        )
    )
    return repo.save(session)


@app.post(f"{settings.api_prefix}/sessions/{{session_id}}/rate", response_model=StudySession)
def rate_interview(session_id: str, repo: SessionRepository = Depends(repo_dependency)):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.INTERVIEW_DONE, SessionState.RESULTS_READY})
    session.state = SessionState.RATING
    item_ratings, factor_ratings = rate_completed_interview(session)
    session.item_ratings = item_ratings
    session.factor_ratings = factor_ratings
    session.state = SessionState.RESULTS_READY
    return repo.save(session)


@app.put(f"{settings.api_prefix}/sessions/{{session_id}}/comparison", response_model=StudySession)
def save_comparison(
    session_id: str,
    payload: ComparisonChoice,
    repo: SessionRepository = Depends(repo_dependency),
):
    session = require_session(session_id, repo)
    require_state(session, {SessionState.RESULTS_READY, SessionState.COMPARISON_DONE})
    session.comparison = payload
    session.state = SessionState.COMPARISON_DONE
    return repo.save(session)

