from .models import Factor, SurveyItem


SURVEY_ITEMS = [
    SurveyItem(id="declarative_1", factor=Factor.DECLARATIVE, text="나는 나의 강점과 약점을 이해한다.", highlighted_for_interview=True),
    SurveyItem(id="declarative_2", factor=Factor.DECLARATIVE, text="나는 정보를 잘 조직한다."),
    SurveyItem(id="declarative_3", factor=Factor.DECLARATIVE, text="나는 정보를 잘 기억한다."),
    SurveyItem(id="procedural_1", factor=Factor.PROCEDURAL, text="나는 과거에 효과가 있었던 전략을 사용한다."),
    SurveyItem(id="procedural_2", factor=Factor.PROCEDURAL, text="나는 사용하는 각 전략마다 구체적인 목적이 있다."),
    SurveyItem(id="procedural_3", factor=Factor.PROCEDURAL, text="나는 공부할 때 어떻게 전략을 사용하는지 알고 있다.", highlighted_for_interview=True),
    SurveyItem(id="conditional_1", factor=Factor.CONDITIONAL, text="나는 그 주제에 대해 이미 아는 것이 있을 때 가장 잘 배운다."),
    SurveyItem(id="conditional_2", factor=Factor.CONDITIONAL, text="나는 필요할 때 스스로 학습 동기를 불러일으킬 수 있다."),
    SurveyItem(id="conditional_3", factor=Factor.CONDITIONAL, text="나는 필요할 때 스스로 공부하게 만들 수 있다."),
    SurveyItem(id="conditional_4", factor=Factor.CONDITIONAL, text="나는 상황에 따라 서로 다른 학습 전략을 사용한다.", highlighted_for_interview=True),
    SurveyItem(id="planning_1", factor=Factor.PLANNING, text="나는 충분한 시간을 확보할 수 있도록 학습 속도를 조절한다."),
    SurveyItem(id="planning_2", factor=Factor.PLANNING, text="나는 과제를 시작하기 전에 구체적인 목표를 세운다.", highlighted_for_interview=True),
    SurveyItem(id="planning_3", factor=Factor.PLANNING, text="나는 시작하기 전에 스스로 질문한다."),
    SurveyItem(id="planning_4", factor=Factor.PLANNING, text="나는 시작하기 전에 문제를 주의 깊게 읽는다.", highlighted_for_interview=True),
    SurveyItem(id="monitoring_1", factor=Factor.MONITORING, text="나는 목표를 달성해가고 있는지 주기적으로 스스로에게 묻는다.", highlighted_for_interview=True),
    SurveyItem(id="monitoring_2", factor=Factor.MONITORING, text="나는 이해 정도를 확인하기 위해 규칙적으로 멈춘다.", highlighted_for_interview=True),
    SurveyItem(id="debugging_1", factor=Factor.DEBUGGING, text="나는 이해하지 못하는 부분이 생기면 전략을 바꾼다."),
    SurveyItem(id="debugging_2", factor=Factor.DEBUGGING, text="나는 수학 공부를 하다가 혼란스러울 때 주어진 자료를 다시 읽는다.", highlighted_for_interview=True),
    SurveyItem(id="debugging_3", factor=Factor.DEBUGGING, text="나는 이해하지 못하는 부분이 생기면 다른 사람에게 도움을 요청한다."),
    SurveyItem(id="debugging_4", factor=Factor.DEBUGGING, text="나는 새로운 정보가 명확하지 않으면 멈추고 다시 살펴본다.", highlighted_for_interview=True),
    SurveyItem(id="evaluation_1", factor=Factor.EVALUATION, text="나는 학습을 마친 뒤 배운 내용을 요약한다.", highlighted_for_interview=True),
    SurveyItem(id="evaluation_2", factor=Factor.EVALUATION, text="나는 과제를 마친 뒤 내가 배울 수 있었던 만큼 충분히 배웠는지 스스로에게 묻는다."),
    SurveyItem(id="evaluation_3", factor=Factor.EVALUATION, text="나는 목표를 얼마나 잘 달성했는지 스스로에게 묻는다.", highlighted_for_interview=True),
]


FACTOR_ORDER = [
    Factor.PLANNING,
    Factor.MONITORING,
    Factor.DEBUGGING,
    Factor.EVALUATION,
    Factor.DECLARATIVE,
    Factor.PROCEDURAL,
    Factor.CONDITIONAL,
]

