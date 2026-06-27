from app.config import Settings
from app.database_url import normalize_database_url


def test_normalize_postgresql_url() -> None:
    raw = "postgresql://user:pass@host:5432/dbname"
    assert normalize_database_url(raw) == "postgresql+psycopg2://user:pass@host:5432/dbname"


def test_normalize_postgres_url() -> None:
    raw = "postgres://user:pass@host:5432/dbname"
    assert normalize_database_url(raw) == "postgresql+psycopg2://user:pass@host:5432/dbname"


def test_keeps_psycopg2_driver() -> None:
    raw = "postgresql+psycopg2://user:pass@localhost:5435/db"
    assert normalize_database_url(raw) == raw


def test_settings_normalizes_railway_database_url() -> None:
    settings = Settings(database_url="postgresql://railway:secret@containers:5432/railway")
    assert settings.database_url.startswith("postgresql+psycopg2://")
    assert settings.database_url.endswith("railway:secret@containers:5432/railway")
