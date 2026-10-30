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
                "당신은 학생의 실제 수학 문제 풀이를 되짚는 회고 인터뷰의 기본 질문을 설계한다. "
                "모든 질문은 제공된 학생 풀이 스키마의 구체적인 개념, 행동, 발화 또는 사건을 근거로 개인화해야 한다. "
                "어느 학생에게나 그대로 사용할 수 있는 일반적인 질문을 만들지 마라. 학생이 하지 않은 행동을 정방향 질문의 사실처럼 제시하지 말고, "
                "학생이 실제로 보인 행동을 정확하게 짚은 뒤 그때의 생각·이유·판단 기준·결과를 회고하게 하라. "
                "질문은 점수를 암시하거나 정답 풀이를 알려주지 않는다. 인지조절 질문은 전사만으로 확인하기 어려운 계획·점검·수정·평가의 실제 생각을 추가 확인한다. "
                "인지지식 질문은 자신의 강점과 약점, 사용한 전략의 실행 방법, 그 전략을 선택한 조건에 대한 학생의 자기이해를 확인한다. "
                "여기서 reverse는 일반적인 설문 역채점 문항이 아니라 학생 풀이 스키마와 반대되는 전제를 의도적으로 제시하는 함정 질문이다. "
                "스키마에서 학생이 한 행동을 하지 않았다고 말하거나, 하지 않은 행동을 했다고 말하거나, 알고 사용한 내용을 모른다고 말하거나, "
                "모르거나 잘못 사용한 내용을 안다고 말하는 방식으로 구성한다. 학생이 그 잘못된 전제를 알아차리고 자신의 실제 풀이를 근거로 바로잡을 수 있는지 확인해야 한다. "
                "함정이라는 사실은 학생에게 밝히지 말고 자연스러운 회고 질문으로 작성하라. reverse 문항의 intent에는 실제 스키마 근거와 질문에서 뒤집은 전제를 명시해 이후 진단이 참조할 수 있게 하라. "
                "정확히 17문항을 만든다: 계획·점검·수정전략·평가 각 2문항, 선언적·절차적·조건적 지식 각 3문항. "
                "선언적·절차적·조건적 지식에는 각각 정확히 한 개의 reverse 문항을 포함하고 나머지는 direct로 만든다. "
                "order는 1부터 17까지이며 모든 status는 pending이다.",
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
        if factor in {Factor.DECLARATIVE, Factor.PROCEDURAL, Factor.CONDITIONAL}:
            reverse_count = sum(item.direction == "reverse" for item in factor_questions)
            if reverse_count != 1:
                raise ValueError(f"Expected exactly one reverse question for {factor.value}")
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
    structured = model.with_structured_output(ItemRating)
    result = structured.invoke(
        [
            (
                "system",
                "당신은 회고 인터뷰 문항별 진단 평가자다. 수학 정답 여부나 답변의 길이가 아니라 해당 문항에서 드러난 역량 수준을 평가한다. "
                "점수는 일반적인 5점 리커트 수준으로 해석한다: 1점 매우 낮음, 2점 낮음, 3점 보통, 4점 높음, 5점 매우 높음. "
                "해당 수준을 판단할 명시적 근거가 부족하면 낮은 점수를 추정하지 말고 unable_to_rate로 처리한다. "
                "인터뷰의 해당 문항에 속한 전체 대화를 주 평가 자료로 사용하고, 학생 풀이 스키마와 전사문은 이를 확인·보완하는 부 자료로 사용한다. "
                "다른 문항에서 나온 답변을 현재 문항의 근거로 가져오지 마라. "
                "direct 문항에서는 학생이 자신의 실제 행동·지식·전략과 그 이유를 얼마나 정확하게 인식하고 설명하는지 평가한다. "
                "reverse 문항은 별도의 역채점 공식을 적용하는 문항이 아니다. 질문의 전제가 학생 풀이 스키마의 실제 모습과 반대라는 점을 고려하여, "
                "학생이 잘못된 전제를 알아차리고 실제 자신의 행동이나 지식을 근거로 바로잡는지, 또는 잘못된 전제에 동의하면서 자기이해의 불일치를 보이는지를 진단 근거로 삼는다. "
                "단순한 동의·부정만으로 점수를 결정하지 말고 설명의 내용과 스키마 근거의 일치 여부를 함께 판단한다. "
                "인터뷰와 스키마·전사의 일치, 보완 또는 상충을 reason에 명시하라.",
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
    # Preserve an auditable reference to every turn supplied to this item-level rating,
    # including the base question, follow-ups, and all student answers.
    result.interview_turn_ids = [turn.id for turn in turns]
    result.rubric_version = get_settings().rubric_version
    valid_segment_ids = {segment.id for segment in session.transcript_segments}
    result.transcript_segment_ids = [item for item in result.transcript_segment_ids if item in valid_segment_ids]
    return result


def rate_items_with_model(session: StudySession) -> list[ItemRating]:
    with ThreadPoolExecutor(max_workers=4) as executor:
        ratings = list(executor.map(lambda question: _rate_one(session, question), session.questions))
    return sorted(ratings, key=lambda item: next(q.order for q in session.questions if q.id == item.question_id))

