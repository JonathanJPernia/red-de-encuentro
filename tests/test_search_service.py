import pytest
from sqlalchemy import select

from app.models import Person
from app.services.normalize_service import hash_document_id, normalize_name
from app.services.search_service import SearchService


def test_search_by_name_with_accents(db_session) -> None:
    person = Person(
        full_name="José María Peña",
        normalized_name=normalize_name("José María Peña"),
        document_id_hash=hash_document_id("99887766"),
        document_id_last4="7766",
    )
    db_session.add(person)
    db_session.commit()

    try:
        service = SearchService(db_session)
        response = service.search("Jose Maria Pena")

        assert response.matches
        assert response.matches[0].full_name == "José María Peña"
        assert response.matches[0].confidence_score >= 95.0
    finally:
        db_session.delete(person)
        db_session.commit()


def test_fuzzy_low_score_returns_no_results(db_session) -> None:
    person = Person(
        full_name="Persona Unica XYZ",
        normalized_name=normalize_name("Persona Unica XYZ"),
    )
    db_session.add(person)
    db_session.commit()

    try:
        service = SearchService(db_session)
        response = service.search("zzzzzzzzzzz")

        assert response.matches == []
    finally:
        db_session.delete(person)
        db_session.commit()


def test_document_formats_match_same_person(db_session) -> None:
    existing = db_session.scalar(
        select(Person).where(Person.full_name == "Juan Carlos Pérez")
    )
    if existing is None:
        pytest.skip("Requiere datos de example_static_scraper")

    service = SearchService(db_session)

    for query in ("12345678", "V-12345678", "12.345.678", "C.I. 12345678"):
        response = service.search(query)
        assert response.matches
        assert response.matches[0].full_name == "Juan Carlos Pérez"
        assert response.matches[0].confidence_score == 100.0
