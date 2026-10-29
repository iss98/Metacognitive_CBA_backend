from app.agents.demo import aggregate_factors, build_question_plan, build_student_schema
from app.models import Factor, ItemRating, StudySession, TranscriptSegment


def test_question_plan_has_seventeen_and_reverse_knowledge_items():
    schema = build_student_schema(
        StudySession(
            participant_code="test",
            transcript_segments=[TranscriptSegment(text="먼저 이항정리를 써서 확인해 보자")],
        )
    )
    questions = build_question_plan(schema)
    assert len(questions) == 17
    assert any("이항정리와" in question.text for question in questions)
    assert any("이항정리를" in question.text for question in questions)
    for factor in [Factor.DECLARATIVE, Factor.PROCEDURAL, Factor.CONDITIONAL]:
        factor_questions = [question for question in questions if question.factor == factor]
        assert len(factor_questions) == 3
        assert any(question.direction == "reverse" for question in factor_questions)
    for factor in [Factor.PLANNING, Factor.MONITORING, Factor.DEBUGGING, Factor.EVALUATION]:
        assert len([question for question in questions if question.factor == factor]) == 2


def test_factor_score_is_item_mean():
    ratings = [
        ItemRating(
            question_id="monitoring_q1",
            factor=Factor.MONITORING,
            question_direction="direct",
            score=4,
            status="rated",
            evidence_alignment="interview_only",
            reason="test",
        ),
        ItemRating(
            question_id="monitoring_q2",
            factor=Factor.MONITORING,
            question_direction="direct",
            score=3,
            status="rated",
            evidence_alignment="interview_only",
            reason="test",
        ),
    ]
    monitoring = next(item for item in aggregate_factors(ratings) if item.factor == Factor.MONITORING)
    assert monitoring.factor_score == 3.5
    assert monitoring.coverage == "complete"

