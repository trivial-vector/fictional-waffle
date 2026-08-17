from app.pipeline.mention_matching import find_mentioned_people, find_touched_commitments


def test_find_mentioned_people_matches_known_names():
    known = {"sarah": "Sarah", "mark": "Mark"}
    text = "I talked to Sarah yesterday and she seemed stressed."

    assert find_mentioned_people(text, known) == {"sarah"}


def test_find_mentioned_people_case_insensitive():
    known = {"sarah": "Sarah"}
    assert find_mentioned_people("I saw SARAH today", known) == {"sarah"}


def test_find_mentioned_people_no_match():
    known = {"sarah": "Sarah"}
    assert find_mentioned_people("I went for a walk.", known) == set()


def test_find_touched_commitments_matches_concerned_person():
    commitments = [
        {"id": "c1", "concerns": ["sarah"]},
        {"id": "c2", "concerns": ["mark"]},
    ]

    touched = find_touched_commitments({"sarah"}, commitments)

    assert [c["id"] for c in touched] == ["c1"]


def test_find_touched_commitments_no_match_returns_empty():
    commitments = [{"id": "c1", "concerns": ["sarah"]}]

    assert find_touched_commitments({"someone_else"}, commitments) == []


def test_find_touched_commitments_handles_missing_concerns_key():
    commitments = [{"id": "c1"}]

    assert find_touched_commitments({"sarah"}, commitments) == []
