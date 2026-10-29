from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import RESOURCE_DIR, get_settings
from ..content import FACTOR_ORDER
from ..models import (
    Factor,
    InterviewQuestion,
    ItemRating,
    StudentSchema,
    StudySession,
)
from .llm import get_chat_model


class QuestionPlan(BaseModel):
    questions: list[InterviewQuestion]


class SufficiencyDecision(BaseModel):
    sufficient: bool
    missing_information: str = ""
    followup: str | None = None


FACTOR_NAMES = {
    Factor.PLANNING: "계획",
    Factor.MONITORING: "점검",
    Factor.DEBUGGING: "수정 전략",
    Factor.EVALUATION: "평가",
    Factor.DECLARATIVE: "선언적 지식",
    Factor.PROCEDURAL: "절차적 지식",
    Factor.CONDITIONAL: "조건적 지식",
}


def _problem_schema() -> dict:
    with (RESOURCE_DIR / "round_table_problem_schema.json").open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _rag_items() -> list[dict]:
    items: list[dict] = []
    for name in ["인지조절.json", "인지지식.json"]:
        with (RESOURCE_DIR / "RAG" / name).open("r", encoding="utf-8") as stream:
            items.extend(json.load(stream))
    return items


def _retrieve_rag() -> list[dict]:
    allowed = {name for name in FACTOR_NAMES.values()}
    selected: list[dict] = []
    counts = {name: 0 for name in allowed}
    for item in _rag_items():
        for factor in item.get("factors", []):
            if factor in allowed and counts[factor] < 4:
                selected.append(item)
                counts[factor] += 1
                break
    return selected


def build_student_schema_with_model(session: StudySession) -> StudentSchema:
    model = get_chat_model()
    if model is None:
        raise RuntimeError("LLM provider is not configured")
    transcript = [segment.model_dump(mode="json") for segment in session.transcript_segments]
    structured = model.with_structured_output(StudentSchema)
    result = structured.invoke(
        [
            (
                "system",
                "당신은 수학 풀이 전사문을 관찰된 사실만으로 구조화하는 에이전트다. "
                "정답 스키마를 보고 학생이 말하지 않은 단계를 보완하지 마라. 모든 사건은 실제 segment id를 인용하라. "
                "수학적 정오와 관계없이 학생이 언급하거나 사용한 개념, 계획, 점검, 수정, 평가 신호를 시간순으로 기록하라.",
            ),
            (
                "human",
                "문제 참조 스키마:\n"
                + json.dumps(_problem_schema(), ensure_ascii=False)
                + "\n\n학생 전사문:\n"
                + json.dumps(transcript, ensure_ascii=False),
            ),
        ]
    )
    result.generated_by = f"{get_settings().llm_provider}-structured-output"
    valid_ids = {segment.id for segment in session.transcript_segments}
    if any(segment_id not in valid_ids for event in result.events for segment_id in event.utterance_ids):
        raise ValueError("Student schema contains a transcript id that does not exist")
    return result


def build_question_plan_with_model(schema: StudentSchema) -> list[InterviewQuestion]:
    model = get_chat_model()
    if model is None:
        raise RuntimeError("LLM provider is not configured")
    structured = model.with_structured_output(QuestionPlan)
    result = structured.invoke(
        [
            (
                "system",
                "당신은 수학 문제 풀이 후 회고 인터뷰의 기본 질문을 설계한다. "
                "질문은 점수를 암시하거나 정답 풀이를 알려주지 않는다. 인지조절은 전사만으로 부족한 실제 생각을 추가 확인한다. "
                "인지지식은 자신의 강점·약점, 전략 실행 방법, 전략 선택 조건을 묻는다. "
                "정확히 17문항을 만든다: 계획·점검·수정전략·평가 각 2문항, 선언적·절차적·조건적 지식 각 3문항. "
                "인지지식 세 factor에는 각각 정확히 한 개 이상의 reverse 문항을 포함한다. order는 1부터 17까지이며 모든 status는 pending이다.",
            ),
            (
                "human",
                "학생 풀이 스키마:\n"
                + schema.model_dump_json()
                + "\n\n승인된 참고 문항:\n"
                + json.dumps(_retrieve_rag(), ensure_ascii=False),
            ),
        ]
    )
    questions = sorted(result.questions, key=lambda item: item.order)
    if len(questions) != 17 or [item.order for item in questions] != list(range(1, 18)):
        raise ValueError("Question plan must contain exactly 17 ordered questions")
    expected = {
        Factor.PLANNING: 2,
        Factor.MONITORING: 2,
        Factor.DEBUGGING: 2,
        Factor.EVALUATION: 2,
        Factor.DECLARATIVE: 3,
        Factor.PROCEDURAL: 3,
        Factor.CONDITIONAL: 3,
    }
    for factor, count in expected.items():
        factor_questions = [item for item in questions if item.factor == factor]
        if len(factor_questions) != count:
            raise ValueError(f"Invalid question count for {factor.value}")
        if factor in {Factor.DECLARATIVE, Factor.PROCEDURAL, Factor.CONDITIONAL} and not any(
            item.direction == "reverse" for item in factor_questions
        ):
            raise ValueError(f"Missing reverse question for {factor.value}")
    return questions


def assess_answer_with_model(
    question: InterviewQuestion,
    previous_answers: list[str],
) -> SufficiencyDecision:
    model = get_chat_model()
    if model is None:
        raise RuntimeError("LLM provider is not configured")
    structured = model.with_structured_output(SufficiencyDecision)
    return structured.invoke(
        [
            (
                "system",
                "현재 기본 질문의 의도에 답할 정보가 충분한지만 판정한다. 점수를 매기지 말고 다음 기본 질문으로 넘어갈지도 판단하지 마라. "
                "상황, 학생의 생각 또는 행동, 이유나 결과 중 핵심이 빠졌을 때만 짧고 중립적인 후속 질문 하나를 제안하라. 정답이나 전략을 암시하지 마라.",
            ),
            (
                "human",
                f"기본 질문: {question.text}\n질문 의도: {question.intent}\n현재까지 답변: "
                + json.dumps(previous_answers, ensure_ascii=False),
            ),
        ]
    )


def _rate_one(session: StudySession, question: InterviewQuestion) -> ItemRating:
    model = get_chat_model()
    if model is None:
        raise RuntimeError("LLM provider is not configured")
    turns = [turn for turn in session.interview_turns if turn.question_id == question.id]
    student_turns = [turn for turn in turns if turn.role == "student"]
    structured = model.with_structured_output(ItemRating)
    result = structured.invoke(
        [
            (
                "system",
                "당신은 문항 단위 메타인지 진단 평가자다. 수학 정답 여부가 아니라 해당 문항에서 드러난 역량의 질을 평가한다. "
                "1점은 학생의 명시적 낮은 근거가 있을 때만 주고, 자료 부족은 unable_to_rate로 처리한다. "
                "2점은 의도만 있고 언제·무엇을·왜 했는지가 모호함, 3점은 구체 장면과 행동·이유가 있으나 실행·효과·한계 일부가 빠짐, "
                "4점은 장면·순서·이유·결과 확인이 일관됨, 5점은 조정 이유·한계·대안·다음 적용까지 설명함을 뜻한다. "
                "역방향 질문도 높은 역량이 높은 점수가 되게 의미를 해석하며 6-원점수 공식을 쓰지 않는다. "
                "전사에 없다는 사실만으로 감점하지 말고 인터뷰와 전사의 일치·보완·상충을 명시하라.",
            ),
            (
                "human",
                "문항:\n"
                + question.model_dump_json()
                + "\n\n이 문항의 인터뷰 턴:\n"
                + json.dumps([turn.model_dump(mode="json") for turn in turns], ensure_ascii=False)
                + "\n\n학생 풀이 스키마:\n"
                + (session.student_schema.model_dump_json() if session.student_schema else "null")
                + "\n\n전사문:\n"
                + json.dumps([segment.model_dump(mode="json") for segment in session.transcript_segments], ensure_ascii=False),
            ),
        ]
    )
    result.question_id = question.id
    result.factor = question.factor
    result.question_direction = question.direction
    result.interview_turn_ids = [turn.id for turn in student_turns]
    result.rubric_version = get_settings().rubric_version
    valid_segment_ids = {segment.id for segment in session.transcript_segments}
    result.transcript_segment_ids = [item for item in result.transcript_segment_ids if item in valid_segment_ids]
    return result


def rate_items_with_model(session: StudySession) -> list[ItemRating]:
    with ThreadPoolExecutor(max_workers=4) as executor:
        ratings = list(executor.map(lambda question: _rate_one(session, question), session.questions))
    return sorted(ratings, key=lambda item: next(q.order for q in session.questions if q.id == item.question_id))

