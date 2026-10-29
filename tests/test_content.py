from app.content import SURVEY_ITEMS


def test_survey_has_23_unique_items():
    assert len(SURVEY_ITEMS) == 23
    assert len({item.id for item in SURVEY_ITEMS}) == 23

