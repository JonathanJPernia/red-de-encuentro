from __future__ import annotations

from rapidfuzz import fuzz

from app.services.normalize_service import normalize_name

SCORE_ALL_TOKENS = 100.0
SCORE_SINGLE_TOKEN_MAX = 80.0
SCORE_TWO_TOKEN_ONE_MATCH_MAX = 65.0
SCORE_TWO_TOKEN_ONE_MATCH_FUZZY_MAX = 70.0
SCORE_MULTI_TOKEN_ONE_MATCH_MAX = 55.0
SCORE_MULTI_TOKEN_PARTIAL_MIN = 85.0
SCORE_MULTI_TOKEN_PARTIAL_MAX = 95.0

# Backward-compatible aliases used in tests/imports.
SCORE_FIRST_AND_LAST = SCORE_ALL_TOKENS
SCORE_TWO_TOKENS = SCORE_MULTI_TOKEN_PARTIAL_MAX
SCORE_SURNAME_ONLY = SCORE_TWO_TOKEN_ONE_MATCH_MAX
SCORE_GIVEN_NAME_ONLY = SCORE_SINGLE_TOKEN_MAX

BROAD_QUERY_MESSAGE = (
    "🔎 Tu búsqueda es demasiado amplia.\n\n"
    "Prueba con:\n"
    "• Nombre completo\n"
    "• Cédula\n"
    "• Nombre + apellido"
)

MIN_SINGLE_TOKEN_LENGTH_FOR_EXTERNAL = 4
MIN_TOKEN_LENGTH = 3
FUZZY_TOKEN_RATIO_THRESHOLD = 88

NAME_STOPWORDS = frozenset(
    {
        "de",
        "del",
        "la",
        "las",
        "los",
        "lo",
        "y",
        "e",
        "da",
        "do",
        "dos",
        "van",
        "von",
    }
)


def tokenize(text: str) -> list[str]:
    normalized = normalize_name(text)
    if not normalized:
        return []
    tokens = normalized.split()
    return [
        token
        for token in tokens
        if len(token) >= MIN_TOKEN_LENGTH and token not in NAME_STOPWORDS
    ]


def is_single_token_query(query: str) -> bool:
    return len(tokenize(query)) == 1


def is_broad_single_word_query(query: str) -> bool:
    tokens = tokenize(query)
    return len(tokens) == 1 and len(tokens[0]) < MIN_SINGLE_TOKEN_LENGTH_FOR_EXTERNAL


def matching_tokens(query_tokens: list[str], name_tokens: list[str]) -> set[str]:
    name_token_set = set(name_tokens)
    return {token for token in query_tokens if token in name_token_set}


def _fuzzy_boost(
    query_tokens: list[str],
    name_tokens: list[str],
    matched: set[str],
    base_score: float,
    max_score: float,
) -> float:
    """Boost score only when at least one token already matches exactly."""
    if not matched:
        return base_score

    unmatched_query = [token for token in query_tokens if token not in matched]
    unmatched_name = [token for token in name_tokens if token not in matched]
    if not unmatched_query or not unmatched_name:
        return base_score

    best_ratio = 0.0
    for query_token in unmatched_query:
        for name_token in unmatched_name:
            best_ratio = max(best_ratio, float(fuzz.ratio(query_token, name_token)))

    if best_ratio < FUZZY_TOKEN_RATIO_THRESHOLD:
        return base_score

    boost = (best_ratio - FUZZY_TOKEN_RATIO_THRESHOLD) / (100 - FUZZY_TOKEN_RATIO_THRESHOLD)
    boosted = base_score + boost * (max_score - base_score)
    return min(round(boosted, 2), max_score)


def _score_multi_token_partial(query_token_count: int, matched_count: int) -> float:
    if matched_count < 2:
        return SCORE_MULTI_TOKEN_PARTIAL_MIN
    ratio = (matched_count - 1) / (query_token_count - 1)
    return round(
        SCORE_MULTI_TOKEN_PARTIAL_MIN
        + ratio * (SCORE_MULTI_TOKEN_PARTIAL_MAX - SCORE_MULTI_TOKEN_PARTIAL_MIN),
        2,
    )


def score_name_match(query: str, full_name: str) -> float | None:
    """
    Puntúa coincidencia por tokens compartidos.

    Retorna None si no hay ningún token en común (descartar).
    """
    query_tokens = tokenize(query)
    name_tokens = tokenize(full_name)
    if not query_tokens or not name_tokens:
        return None

    if normalize_name(query) == normalize_name(full_name):
        return SCORE_ALL_TOKENS

    matched = matching_tokens(query_tokens, name_tokens)
    if not matched:
        return None

    query_token_count = len(query_tokens)
    matched_count = len(matched)

    if query_token_count == 1:
        token = query_tokens[0]
        if token not in name_tokens:
            return None
        return SCORE_SINGLE_TOKEN_MAX

    if query_token_count == 2:
        if matched_count == 2:
            return SCORE_ALL_TOKENS
        return _fuzzy_boost(
            query_tokens,
            name_tokens,
            matched,
            SCORE_TWO_TOKEN_ONE_MATCH_MAX,
            SCORE_TWO_TOKEN_ONE_MATCH_FUZZY_MAX,
        )

    if matched_count == query_token_count:
        return SCORE_ALL_TOKENS
    if matched_count >= 2:
        return _score_multi_token_partial(query_token_count, matched_count)
    return _fuzzy_boost(
        query_tokens,
        name_tokens,
        matched,
        SCORE_MULTI_TOKEN_ONE_MATCH_MAX,
        SCORE_MULTI_TOKEN_ONE_MATCH_MAX,
    )


def min_score_for_query(query: str) -> float:
    """Umbral mínimo de score para incluir un resultado."""
    if is_single_token_query(query):
        return SCORE_SINGLE_TOKEN_MAX
    return SCORE_TWO_TOKEN_ONE_MATCH_FUZZY_MAX
