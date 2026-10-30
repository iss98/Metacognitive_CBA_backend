from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionState(StrEnum):
    AUDIO_CHECK = "audio_check"
    CREATED = "created"
    SURVEY_DONE = "survey_done"
    RECORDING = "recording"
    TRANSCRIPT_READY = "transcript_ready"
    SCHEMA_READY = "schema_ready"
    QUESTIONS_READY = "questions_ready"
    INTERVIEWING = "interviewing"
    INTERVIEW_DONE = "interview_done"
    RATING = "rating"
    RESULTS_READY = "results_ready"
    COMPARISON_DONE = "comparison_done"


class Factor(StrEnum):
    PLANNING = "planning"
    MONITORING = "monitoring"
    DEBUGGING = "debugging"
    EVALUATION = "evaluation"
    DECLARATIVE = "declarative_knowledge"
    PROCEDURAL = "procedural_knowledge"
    CONDITIONAL = "conditional_knowledge"


FACTOR_LABELS: dict[Factor, str] = {
    Factor.PLANNING: "계획",
    Factor.MONITORING: "점검",
    Factor.DEBUGGING: "수정 전략",
    Factor.EVALUATION: "평가",
    Factor.DECLARATIVE: "선언적 지식",
    Factor.PROCEDURAL: "절차적 지식",
    Factor.CONDITIONAL: "조건적 지식",
}


class SurveyItem(BaseModel):
    id: str
    factor: Factor
    text: str
    highlighted_for_interview: bool = False


class SurveyResponse(BaseModel):
    item_id: str
    score: int = Field(ge=1, le=5)
    factor: Factor | None = None
    display_order: int | None = Field(default=None, ge=1)


class SurveySubmission(BaseModel):
    responses: list[SurveyResponse]


class AudioCheckSubmission(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)


class AudioCheckResult(BaseModel):
    expected_text: str
    transcript: str
    normalized_match: bool
    completed_at: datetime = Field(default_factory=utc_now)


class TranscriptSegment(BaseModel):
    id: str = Field(default_factory=lambda: f"seg_{uuid4().hex[:10]}")
    item_id: str | None = None
    order: int = 0
    text: str = Field(min_length=1)
    source: Literal["realtime", "file_recovery", "manual"] = "realtime"
    created_at: datetime = Field(default_factory=utc_now)


class TranscriptSubmission(BaseModel):
    segments: list[TranscriptSegment]


class StudentEvent(BaseModel):
    id: str
    situation: str
    utterance_ids: list[str]
    action: str
    math_tags: list[str] = Field(default_factory=list)
    regulation_tags: list[Factor] = Field(default_factory=list)
    uncertain: bool = False


class StudentSchema(BaseModel):
    final_answer: str | None = None
    mentioned_concepts: list[str] = Field(default_factory=list)
    events: list[StudentEvent] = Field(default_factory=list)
    generated_by: str = "demo-structured-parser"


class InterviewQuestion(BaseModel):
    id: str
    order: int
    factor: Factor
    text: str
    direction: Literal["direct", "reverse"] = "direct"
    intent: str
    source_item_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "active", "answered"] = "pending"
    followup_count: int = 0


class InterviewTurn(BaseModel):
    id: str = Field(default_factory=lambda: f"turn_{uuid4().hex[:10]}")
    question_id: str
    role: Literal["assistant", "student"]
    text: str
    kind: Literal["base_question", "followup", "answer"]
    created_at: datetime = Field(default_factory=utc_now)


class InterviewAnswer(BaseModel):
    question_id: str
    text: str = Field(min_length=1, max_length=5000)


class ItemRating(BaseModel):
    question_id: str
    factor: Factor
    question_direction: Literal["direct", "reverse"]
    score: int | None = Field(default=None, ge=1, le=5)
    status: Literal["rated", "unable_to_rate"]
    interview_turn_ids: list[str] = Field(default_factory=list)
    transcript_segment_ids: list[str] = Field(default_factory=list)
    evidence_alignment: Literal[
        "corroborated",
        "complementary",
        "interview_only",
        "transcript_only",
        "in_tension",
        "insufficient",
    ]
    response_consistency: Literal[
        "consistent", "contextually_explained", "inconsistent", "not_comparable"
    ] = "not_comparable"
    reason: str
    uncertainty: str | None = None
    rubric_version: str = "draft-3"


class FactorRating(BaseModel):
    factor: Factor
    item_scores: list[dict[str, int | str | None]]
    factor_score: float | None
    rated_item_count: int
    total_item_count: int
    coverage: Literal["complete", "partial", "insufficient"]
    aggregation: Literal["arithmetic_mean"] = "arithmetic_mean"
    rubric_version: str = "draft-3"


class ComparisonChoice(BaseModel):
    choice: Literal["survey", "interview", "both", "neither"]
    note: str = Field(default="", max_length=2000)


class StudySession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    participant_code: str
    state: SessionState = SessionState.AUDIO_CHECK
    state_version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    audio_check: AudioCheckResult | None = None
    survey_order: list[str] = Field(default_factory=list)
    survey_responses: list[SurveyResponse] = Field(default_factory=list)
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    audio_path: str | None = None
    student_schema: StudentSchema | None = None
    questions: list[InterviewQuestion] = Field(default_factory=list)
    interview_turns: list[InterviewTurn] = Field(default_factory=list)
    current_question_index: int = 0
    item_ratings: list[ItemRating] = Field(default_factory=list)
    factor_ratings: list[FactorRating] = Field(default_factory=list)
    comparison: ComparisonChoice | None = None
    execution_mode: Literal["demo", "model"] = "demo"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    participant_code: str = Field(min_length=1, max_length=80)


class SessionSummary(BaseModel):
    id: str
    participant_code: str
    state: SessionState
    updated_at: datetime
    execution_mode: Literal["demo", "model"]

