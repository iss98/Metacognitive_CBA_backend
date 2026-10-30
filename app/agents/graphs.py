from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..models import FactorRating, InterviewQuestion, ItemRating, StudentSchema, StudySession
from .demo import aggregate_factors, build_question_plan, build_student_schema, rate_items
from .model import build_question_plan_with_model, build_student_schema_with_model, rate_items_with_model
from ..config import get_settings


class PrepareState(TypedDict, total=False):
    session: StudySession
    student_schema: StudentSchema
    questions: list[InterviewQuestion]


def _schema_node(state: PrepareState) -> PrepareState:
    if get_settings().llm_provider == "mock":
        return {"student_schema": build_student_schema(state["session"])}
    return {"student_schema": build_student_schema_with_model(state["session"])}


def _question_node(state: PrepareState) -> PrepareState:
    if get_settings().llm_provider == "mock":
        return {"questions": build_question_plan(state["student_schema"])}
    return {"questions": build_question_plan_with_model(state["student_schema"])}


prepare_builder = StateGraph(PrepareState)
prepare_builder.add_node("student_schema_agent", _schema_node)
prepare_builder.add_node("question_design_agent", _question_node)
prepare_builder.add_edge(START, "student_schema_agent")
prepare_builder.add_edge("student_schema_agent", "question_design_agent")
prepare_builder.add_edge("question_design_agent", END)
PREPARE_GRAPH = prepare_builder.compile()


class RatingState(TypedDict, total=False):
    session: StudySession
    item_ratings: list[ItemRating]
    factor_ratings: list[FactorRating]


def _item_rating_node(state: RatingState) -> RatingState:
    if get_settings().llm_provider == "mock":
        return {"item_ratings": rate_items(state["session"])}
    return {"item_ratings": rate_items_with_model(state["session"])}


def _aggregate_node(state: RatingState) -> RatingState:
    return {"factor_ratings": aggregate_factors(state["item_ratings"])}


rating_builder = StateGraph(RatingState)
rating_builder.add_node("item_diagnosis_agents", _item_rating_node)
rating_builder.add_node("factor_aggregation", _aggregate_node)
rating_builder.add_edge(START, "item_diagnosis_agents")
rating_builder.add_edge("item_diagnosis_agents", "factor_aggregation")
rating_builder.add_edge("factor_aggregation", END)
RATING_GRAPH = rating_builder.compile()


def prepare_interview_assets(session: StudySession) -> tuple[StudentSchema, list[InterviewQuestion]]:
    result = PREPARE_GRAPH.invoke(
        {"session": session},
        config={
            "run_name": "mccba_prepare_interview",
            "tags": ["mccba", "prepare-interview", session.execution_mode],
            "metadata": {"session_id": session.id, "state": session.state.value},
        },
    )
    return result["student_schema"], result["questions"]


def rate_completed_interview(session: StudySession) -> tuple[list[ItemRating], list[FactorRating]]:
    result = RATING_GRAPH.invoke(
        {"session": session},
        config={
            "run_name": "mccba_rate_interview",
            "tags": ["mccba", "rating", session.execution_mode],
            "metadata": {"session_id": session.id, "state": session.state.value},
        },
    )
    return result["item_ratings"], result["factor_ratings"]

