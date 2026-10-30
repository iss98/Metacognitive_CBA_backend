import re
from collections import defaultdict

from ..config import get_settings
from ..content import FACTOR_ORDER
from ..models import (
    Factor,
    FactorRating,
    InterviewQuestion,
    ItemRating,
    StudentEvent,
    StudentSchema,
    StudySession,
)


CONCEPT_KEYWORDS = {
    "이항정리": ["이항", "전개"],
    "조합": ["조합", "nC", "경우의 수"],
    "전이행렬": ["행렬", "고유값", "대각합", "trace"],
    "형 전환 경계": ["경계", "바뀌", "전환"],
    "복소수의 덧셈": ["허수", "실수", "i", "-i"],
}


def with_particle(word: str, consonant_form: str, vowel_form: str) -> str:
    last = word[-1]
    if "가" <= last <= "힣":
        has_final_consonant = (ord(last) - ord("가")) % 28 != 0
        return f"{word}{consonant_form if has_final_consonant else vowel_form}"
    return f"{word}{vowel_form}"


def build_student_schema(session: StudySession) -> StudentSchema:
    full_text = " ".join(segment.text for segment in session.transcript_segments)
    concepts = [
        name
        for name, keywords in CONCEPT_KEYWORDS.items()
        if any(keyword.lower() in full_text.lower() for keyword in keywords)
    ]
    events: list[StudentEvent] = []
    for index, segment in enumerate(session.transcript_segments, start=1):
        text = segment.text
        regulation_tags: list[Factor] = []
        if any(word in text for word in ["먼저", "계획", "순서", "해보자"]):
            regulation_tags.append(Factor.PLANNING)
        if any(word in text for word in ["확인", "맞나", "다시 계산", "조건"]):
            regulation_tags.append(Factor.MONITORING)
        if any(word in text for word in ["아니다", "바꿔", "다시 읽", "다른 방법"]):
            regulation_tags.append(Factor.DEBUGGING)
        if any(word in text for word in ["결론", "검산", "답은", "정리하면"]):
            regulation_tags.append(Factor.EVALUATION)
        math_tags = [
            name
            for name, keywords in CONCEPT_KEYWORDS.items()
            if any(keyword.lower() in text.lower() for keyword in keywords)
        ]
        events.append(
            StudentEvent(
                id=f"event_{index:02d}",
                situation="학생이 풀이를 이어감",
                utterance_ids=[segment.id],
                action=text,
                math_tags=math_tags,
                regulation_tags=regulation_tags,
                uncertain=False,
            )
        )
    answer_match = re.findall(r"(?:답은|결과는|정리하면)\s*([^.!?]+)", full_text)
    return StudentSchema(
        final_answer=answer_match[-1].strip() if answer_match else None,
        mentioned_concepts=concepts,
        events=events,
    )


def build_question_plan(schema: StudentSchema) -> list[InterviewQuestion]:
    concept = schema.mentioned_concepts[0] if schema.mentioned_concepts else "이 문제의 핵심 개념"
    observed_action = schema.events[0].action if schema.events else "문제의 조건을 이용해 풀이를 진행한 것"
    specs = [
        (Factor.PLANNING, "direct", "문제를 처음 읽었을 때 무엇을 구해야 한다고 정리했고, 풀이를 시작하기 전에 어떤 계획을 세웠나요?", "목표 설정과 사전 계획"),
        (Factor.PLANNING, "direct", "계산을 시작하기 전에 문제의 조건을 어떻게 확인했고, 어떤 순서로 풀기로 했나요?", "조건 확인과 실행 순서"),
        (Factor.MONITORING, "direct", "풀이 중에 지금 접근이 맞는지 확인한 순간이 있었나요? 무엇을 기준으로 확인했나요?", "진행 점검의 시점과 기준"),
        (Factor.MONITORING, "direct", "이웃한 두 수의 조건이나 계산 결과를 중간에 다시 살펴본 장면을 설명해 주세요.", "이해와 계산의 점검"),
        (Factor.DEBUGGING, "direct", "풀이가 막히거나 혼란스러웠던 순간에 무엇이 문제라고 생각했고 어떻게 대처했나요?", "혼란 탐지와 대처"),
        (Factor.DEBUGGING, "direct", "처음 방법을 바꾸거나 문제를 다시 읽은 적이 있다면, 왜 그렇게 했고 이후 무엇이 달라졌나요?", "전략 변경의 이유와 효과"),
        (Factor.EVALUATION, "direct", "답을 낸 뒤 그 답이 문제의 모든 조건에 맞는지 어떻게 확인했나요?", "최종 결과 검토"),
        (Factor.EVALUATION, "direct", "풀이를 마치고 나서 더 나은 방법이나 다음에 달리할 점을 생각했나요?", "풀이 회고와 다음 적용"),
        (Factor.DECLARATIVE, "direct", f"이번 풀이에서 {with_particle(concept, '과', '와')} 관련해 자신이 잘 이해했다고 생각한 부분은 무엇인가요?", "자신의 강점 인식"),
        (Factor.DECLARATIVE, "direct", "이번 문제에서 자신에게 가장 어려웠던 개념이나 약점은 무엇이었고, 그렇게 판단한 근거는 무엇인가요?", "자신의 약점 인식"),
        (Factor.DECLARATIVE, "reverse", f"풀이를 보면 {with_particle(concept, '을', '를')} 전혀 알지 못한 채 사용한 것처럼 보이는데, 실제로도 그랬나요? 당시 풀이를 근거로 설명해 주세요.", f"스키마에는 {concept}의 언급 또는 사용이 기록되어 있으나 이를 알지 못했다고 뒤집어 제시하여 자기지식의 정확성을 확인"),
        (Factor.PROCEDURAL, "direct", "이번 문제에서 사용한 핵심 전략을 실제로 어떤 순서로 실행했는지 설명해 주세요.", "전략 실행 절차"),
        (Factor.PROCEDURAL, "direct", "그 전략의 각 단계에는 어떤 목적이 있었고, 제대로 실행됐는지는 어떻게 알았나요?", "전략 목적과 확인 방법"),
        (Factor.PROCEDURAL, "reverse", f"풀이에서는 '{observed_action}'과 같은 절차를 따로 사용하지 않고 바로 답을 정한 것처럼 보이는데, 실제로도 그랬나요?", f"스키마에 기록된 행동 '{observed_action}'을 하지 않았다고 뒤집어 제시하여 절차에 대한 자기이해를 확인"),
        (Factor.CONDITIONAL, "direct", "여러 방법 중에서 이번 방법을 선택한 이유는 무엇이며, 어떤 문제 조건이 그 선택에 영향을 주었나요?", "전략 선택 조건"),
        (Factor.CONDITIONAL, "direct", "문제 조건이 어떻게 달라지면 다른 전략을 선택할 것 같나요? 구체적인 예를 들어 주세요.", "전략 전환 조건"),
        (Factor.CONDITIONAL, "reverse", f"'{observed_action}'이라는 방법은 문제 조건과 관계없이 우연히 선택한 것 같은데, 실제로도 조건을 고려하지 않았나요?", f"스키마에 기록된 전략 행동 '{observed_action}'과 문제 조건의 관련성을 부정하여 전략 선택 조건에 대한 자기이해를 확인"),
    ]
    return [
        InterviewQuestion(
            id=f"{factor.value}_q{sum(1 for prior in specs[: index - 1] if prior[0] == factor) + 1}",
            order=index,
            factor=factor,
            direction=direction,
            text=text,
            intent=intent,
            source_item_ids=[],
        )
        for index, (factor, direction, text, intent) in enumerate(specs, start=1)
    ]


def make_followup(question: InterviewQuestion) -> str:
    return (
        "그때의 구체적인 장면을 하나 떠올려 주세요. "
        "무엇을 생각했고, 실제로 무엇을 했으며, 그 결과를 어떻게 확인했는지 차례로 말해 주세요."
    )


def is_answer_sufficient(text: str) -> bool:
    stripped = text.strip()
    detail_markers = ["왜", "그래서", "때문", "확인", "다시", "먼저", "다음", "결과"]
    return len(stripped) >= 45 or (len(stripped) >= 25 and any(marker in stripped for marker in detail_markers))


def _related_transcript_ids(session: StudySession, answer: str) -> list[str]:
    tokens = {token for token in re.findall(r"[가-힣A-Za-z0-9]+", answer) if len(token) >= 2}
    scored: list[tuple[int, str]] = []
    for segment in session.transcript_segments:
        overlap = sum(1 for token in tokens if token in segment.text)
        if overlap:
            scored.append((overlap, segment.id))
    return [segment_id for _, segment_id in sorted(scored, reverse=True)[:3]]


def rate_items(session: StudySession) -> list[ItemRating]:
    settings = get_settings()
    turns_by_question: dict[str, list] = defaultdict(list)
    for turn in session.interview_turns:
        turns_by_question[turn.question_id].append(turn)

    ratings: list[ItemRating] = []
    for question in session.questions:
        turns = turns_by_question.get(question.id, [])
        student_turns = [turn for turn in turns if turn.role == "student"]
        answer = " ".join(turn.text for turn in student_turns).strip()
        transcript_ids = _related_transcript_ids(session, answer)
        if not answer:
            ratings.append(
                ItemRating(
                    question_id=question.id,
                    factor=question.factor,
                    question_direction=question.direction,
                    status="unable_to_rate",
                    interview_turn_ids=[turn.id for turn in turns],
                    transcript_segment_ids=[],
                    evidence_alignment="insufficient",
                    reason="질문에 대한 학생 응답이 없어 평가할 수 없습니다.",
                    uncertainty="데모 채점: 실제 연구에서는 사람 평가자와 모델 검증이 필요합니다.",
                    rubric_version=settings.rubric_version,
                )
            )
            continue

        score = 2
        if len(answer) >= 25:
            score = 3
        if len(answer) >= 80 and any(word in answer for word in ["왜", "때문", "확인", "결과", "다시"]):
            score = 4
        if len(answer) >= 160 and sum(word in answer for word in ["왜", "때문", "확인", "결과", "다시", "다음", "한계"]) >= 3:
            score = 5
        ratings.append(
            ItemRating(
                question_id=question.id,
                factor=question.factor,
                question_direction=question.direction,
                score=score,
                status="rated",
                interview_turn_ids=[turn.id for turn in turns],
                transcript_segment_ids=transcript_ids,
                evidence_alignment="corroborated" if transcript_ids else "interview_only",
                response_consistency="not_comparable",
                reason=(
                    "학생이 구체적 장면과 행동을 설명한 정도를 데모 규칙으로 평정했습니다. "
                    "실제 연구 점수로 사용하기 전에 모델 기반 루브릭과 사람 평가자 일치도를 검증해야 합니다."
                ),
                uncertainty="현재 결과는 UI·데이터 흐름 검증용 데모 채점입니다.",
                rubric_version=settings.rubric_version,
            )
        )
    return ratings


def aggregate_factors(item_ratings: list[ItemRating]) -> list[FactorRating]:
    settings = get_settings()
    results: list[FactorRating] = []
    for factor in FACTOR_ORDER:
        items = [item for item in item_ratings if item.factor == factor]
        valid = [item for item in items if item.score is not None]
        required = 2
        if len(valid) < required:
            factor_score = None
            coverage = "insufficient"
        else:
            factor_score = round(sum(item.score for item in valid if item.score is not None) / len(valid), 2)
            coverage = "complete" if len(valid) == len(items) else "partial"
        results.append(
            FactorRating(
                factor=factor,
                item_scores=[{"question_id": item.question_id, "score": item.score} for item in items],
                factor_score=factor_score,
                rated_item_count=len(valid),
                total_item_count=len(items),
                coverage=coverage,
                rubric_version=settings.rubric_version,
            )
        )
    return results

