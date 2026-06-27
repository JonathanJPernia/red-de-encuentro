"""Normalización de DATABASE_URL para distintos entornos (Railway, Heroku, local)."""


def normalize_database_url(url: str) -> str:
    """
    Convierte URLs postgres/postgresql sin driver al formato SQLAlchemy + psycopg2.

    Railway suele proveer ``postgresql://...`` o ``postgres://...``.
    SQLAlchemy requiere ``postgresql+psycopg2://...``.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url.removeprefix("postgres://")

    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return "postgresql+psycopg2://" + url.removeprefix("postgresql://")

    return url
