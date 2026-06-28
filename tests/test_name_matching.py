import pytest

from app.services.name_matching import (
    BROAD_QUERY_MESSAGE,
    SCORE_ALL_TOKENS,
    SCORE_FIRST_AND_LAST,
    SCORE_GIVEN_NAME_ONLY,
    SCORE_SURNAME_ONLY,
    SCORE_TWO_TOKENS,
    is_broad_single_word_query,
    matching_tokens,
    score_name_match,
    tokenize,
)
from app.services.search_service import SearchService


def test_tokenize_query() -> None:
    assert tokenize("Juan Carlos Perez") == ["juan", "carlos", "perez"]


def test_zero_common_tokens_discarded() -> None:
    assert score_name_match("Juan Perez", "Emily Estefania Ramos Vargas") is None
    assert matching_tokens(tokenize("Juan Perez"), tokenize("Emily Estefania Ramos Vargas")) == set()


def test_juan_perez_never_matches_emily() -> None:
    score = score_name_match("Juan Perez", "Emily Estefanía Ramos Vargas")
    assert score is None


def test_all_tokens_match_scores_100() -> None:
    assert score_name_match("Juan Carlos Perez", "Juan Carlos Perez") == SCORE_ALL_TOKENS
    assert score_name_match("Juan Perez", "Juan Carlos Perez") == SCORE_ALL_TOKENS


def test_first_and_last_scores_98() -> None:
    assert score_name_match("Juan Garcia Perez", "Juan Maria Perez") == SCORE_FIRST_AND_LAST


def test_two_tokens_scores_95() -> None:
    assert score_name_match("Carlos Perez Maria", "Carlos Perez Juan") == SCORE_TWO_TOKENS


def test_surname_only_scores_90() -> None:
    assert score_name_match("Perez", "Maria Perez") == SCORE_SURNAME_ONLY
    assert score_name_match("Juan Perez", "Maria Perez") == SCORE_SURNAME_ONLY


def test_given_name_only_scores_80() -> None:
    assert score_name_match("Juan", "Juan Carlos") == SCORE_GIVEN_NAME_ONLY
    assert score_name_match("Juan Perez", "Juan Maria") == SCORE_GIVEN_NAME_ONLY


def test_single_word_contains_only() -> None:
    assert score_name_match("Juan", "Juan Carlos") == SCORE_GIVEN_NAME_ONLY
    assert score_name_match("Juan", "Juan Jose") == SCORE_GIVEN_NAME_ONLY
    assert score_name_match("Juan", "Emily Estefania") is None
    assert score_name_match("Juan", "Maria Carlos") is None


def test_ranking_favors_complete_matches() -> None:
    scores = [
        score_name_match("Juan Perez", "Juan Carlos Perez"),
        score_name_match("Juan Perez", "Juan Maria"),
        score_name_match("Juan Perez", "Maria Perez"),
    ]
    assert scores == [SCORE_ALL_TOKENS, SCORE_GIVEN_NAME_ONLY, SCORE_SURNAME_ONLY]
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_broad_single_word_query() -> None:
    assert is_broad_single_word_query("Ana") is True
    assert is_broad_single_word_query("Juan") is False


def test_broad_query_raises_in_search_service(db_session) -> None:
    service = SearchService(db_session)
    with pytest.raises(ValueError, match="demasiado amplia"):
        service.search("Ana")


def test_juan_perez_filters_unrelated_local_results(db_session, monkeypatch) -> None:
    from app.config import get_settings
    from app.models import Person
    from app.services.normalize_service import normalize_name

    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "false")
    get_settings.cache_clear()

    unrelated = Person(
        full_name="Emily Estefanía Ramos Vargas",
        normalized_name=normalize_name("Emily Estefanía Ramos Vargas"),
    )
    related = Person(
        full_name="Juan Carlos Perez",
        normalized_name=normalize_name("Juan Carlos Perez"),
    )
    db_session.add_all([unrelated, related])
    db_session.commit()

    try:
        response = SearchService(db_session).search("Juan Perez")
        names = [match.full_name for match in response.matches]
        assert "Emily Estefanía Ramos Vargas" not in names
        assert any("Juan Carlos Perez" in name or "Juan Carlos Pérez" in name for name in names)
        juan_match = next(match for match in response.matches if "Juan Carlos" in match.full_name)
        assert juan_match.confidence_score == SCORE_ALL_TOKENS
    finally:
        db_session.delete(unrelated)
        db_session.delete(related)
        db_session.commit()


def test_single_word_juan_matches_juan_names(db_session, monkeypatch) -> None:
    from app.config import get_settings
    from app.models import Person
    from app.services.normalize_service import normalize_name

    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "false")
    get_settings.cache_clear()

    person = Person(
        full_name="Juan David Lopez",
        normalized_name=normalize_name("Juan David Lopez"),
    )
    db_session.add(person)
    db_session.commit()

    try:
        response = SearchService(db_session).search("Juan")
        juan_matches = [match for match in response.matches if match.full_name == "Juan David Lopez"]
        assert len(juan_matches) == 1
    finally:
        db_session.delete(person)
        db_session.commit()
