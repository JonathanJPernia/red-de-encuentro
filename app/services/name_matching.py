from __future__ import annotations

from app.services.normalize_service import normalize_name

SCORE_ALL_TOKENS = 100.0
SCORE_FIRST_AND_LAST = 98.0
SCORE_TWO_TOKENS = 95.0
SCORE_SURNAME_ONLY = 90.0
SCORE_GIVEN_NAME_ONLY = 80.0

BROAD_QUERY_MESSAGE = (
    "🔎 Tu búsqueda es demasiado amplia.\n\n"
    "Prueba con:\n"
    "• Nombre completo\n"
    "• Cédula\n"
    "• Nombre + apellido"
)

MIN_SINGLE_TOKEN_LENGTH_FOR_EXTERNAL = 4


def tokenize(text: str) -> list[str]:
    normalized = normalize_name(text)
    if not normalized:
        return []
    return normalized.split()


def is_single_token_query(query: str) -> bool:
    return len(tokenize(query)) == 1


def is_broad_single_word_query(query: str) -> bool:
    tokens = tokenize(query)
    return len(tokens) == 1 and len(tokens[0]) < MIN_SINGLE_TOKEN_LENGTH_FOR_EXTERNAL


def matching_tokens(query_tokens: list[str], name_tokens: list[str]) -> set[str]:
    name_token_set = set(name_tokens)
    return {token for token in query_tokens if token in name_token_set}


def score_name_match(query: str, full_name: str) -> float | None:
    """
    Puntúa coincidencia por tokens compartidos.

    Retorna None si no hay ningún token en común (descartar).
    """
    query_tokens = tokenize(query)
    name_tokens = tokenize(full_name)
    if not query_tokens or not name_tokens:
        return None

    matched = matching_tokens(query_tokens, name_tokens)
    if not matched:
        return None

    if len(query_tokens) == 1:
        token = query_tokens[0]
        if token not in name_tokens:
            return None
        if token == name_tokens[-1] and token != name_tokens[0]:
            return SCORE_SURNAME_ONLY
        return SCORE_GIVEN_NAME_ONLY

    if len(matched) == len(query_tokens):
        return SCORE_ALL_TOKENS

    first_token = query_tokens[0]
    last_token = query_tokens[-1]
    first_matches = first_token in name_tokens
    last_matches = last_token in name_tokens

    if first_matches and last_matches:
        return SCORE_FIRST_AND_LAST

    if len(matched) >= 2:
        return SCORE_TWO_TOKENS

    if last_matches:
        return SCORE_SURNAME_ONLY

    if first_matches:
        return SCORE_GIVEN_NAME_ONLY

    return None
