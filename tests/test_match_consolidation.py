from datetime import datetime

from app.bot.response_format import BOT_MAX_SOURCE_LINKS, format_bot_match
from app.schemas.search import PersonMatch, SourceMatch
from app.services.match_consolidation import (
    consolidate_group,
    consolidate_matches,
    consolidate_status,
    rank_matches,
    should_merge,
)
from app.services.normalize_service import hash_document_id


def _source(
    name: str,
    status: str,
    *,
    url: str | None = None,
    published_at: datetime | None = None,
) -> SourceMatch:
    return SourceMatch(
        name=name,
        status=status,
        source_url=url or f"https://example.com/{name.lower().replace(' ', '-')}",
        published_at=published_at,
    )


def _match(
    full_name: str,
    *,
    document_id: str | None = None,
    confidence: float = 95.0,
    sources: list[SourceMatch] | None = None,
) -> PersonMatch:
    last4 = None
    doc_hash = None
    if document_id:
        last4 = document_id[-4:]
        doc_hash = hash_document_id(document_id)

    return PersonMatch(
        full_name=full_name,
        document_id_last4=last4,
        document_id_hash=doc_hash,
        confidence_score=confidence,
        sources=sources or [_source("Fuente A", "missing")],
    )


def test_same_document_hash_groups_matches() -> None:
    left = _match("Juan Pérez", document_id="12345678", sources=[_source("Red Ayuda", "missing")])
    right = _match(
        "Juan Carlos Pérez",
        document_id="12345678",
        sources=[_source("Localizados Venezuela", "found")],
    )

    consolidated = consolidate_matches([left, right])

    assert len(consolidated) == 1
    assert consolidated[0].source_count == 2
    assert {source.name for source in consolidated[0].sources} == {
        "Red Ayuda",
        "Localizados Venezuela",
    }


def test_similar_names_without_document_group_at_94() -> None:
    left = _match(
        "Maria Fernanda Lopez",
        sources=[_source("Emergencia Joch", "missing")],
    )
    right = _match(
        "Maria Fernanda López",
        sources=[_source("Venezuela Te Busca", "missing")],
    )

    assert should_merge(left, right) is True
    consolidated = consolidate_matches([left, right])
    assert len(consolidated) == 1


def test_similar_but_distinct_names_do_not_group() -> None:
    left = _match("Ana María Rodríguez")
    right = _match("Ana María González")

    assert should_merge(left, right) is False
    assert len(consolidate_matches([left, right])) == 2


def test_found_wins_over_missing() -> None:
    left = _match("Juan Pérez", sources=[_source("Fuente A", "missing")])
    right = _match("Juan Pérez", sources=[_source("Fuente B", "found")])

    status, conflict = consolidate_status(["missing", "found"])
    assert status == "found"
    assert conflict is True

    consolidated = consolidate_group([left, right])
    assert consolidated.status == "found"


def test_status_conflict_when_sources_disagree() -> None:
    left = _match("Juan Pérez", sources=[_source("Fuente A", "missing")])
    right = _match("Juan Pérez", sources=[_source("Fuente B", "found")])

    consolidated = consolidate_matches([left, right])[0]
    assert consolidated.status_conflict is True


def test_ranking_prefers_exact_document_and_more_sources() -> None:
    exact = _match(
        "Juan Pérez",
        document_id="12345678",
        confidence=100.0,
        sources=[
            _source("Fuente A", "found"),
            _source("Fuente B", "found"),
        ],
    )
    partial = _match("Juan Perez", confidence=80.0, sources=[_source("Fuente C", "missing")])

    ranked = rank_matches([partial, exact], "12345678")
    assert ranked[0].document_id_last4 == "5678"


def test_bot_shows_single_consolidated_card() -> None:
    consolidated = consolidate_matches(
        [
            _match("Juan Pérez", sources=[_source("Fuente A", "missing")]),
            _match("Juan Pérez", sources=[_source("Fuente B", "found")]),
        ]
    )[0]

    text = format_bot_match(1, consolidated)

    assert "1️⃣ Juan Pérez" in text
    assert text.count("1️⃣") == 1
    assert "📚 Fuentes: 2" in text
    assert "🟢 Estado: Localizado/a" in text
    assert "found" not in text


def test_bot_shows_status_conflict_warning() -> None:
    consolidated = consolidate_matches(
        [
            _match("Juan Pérez", sources=[_source("Fuente A", "missing")]),
            _match("Juan Pérez", sources=[_source("Fuente B", "found")]),
        ]
    )[0]

    text = format_bot_match(1, consolidated)
    assert "estados diferentes" in text


def test_bot_shows_max_three_links() -> None:
    sources = [_source(f"Fuente {index}", "missing", url=f"https://example.com/{index}") for index in range(5)]
    match = PersonMatch(
        full_name="Juan Pérez",
        confidence_score=95.0,
        status="missing",
        source_count=len(sources),
        sources=sources,
    )

    text = format_bot_match(1, match)
    assert text.count("🔗 Fuente") == BOT_MAX_SOURCE_LINKS
    assert "https://example.com/4" not in text
