import pytest

from app.services.normalize_service import (
    document_id_last4,
    hash_document_id,
    normalize_document_id,
    normalize_name,
    normalize_status,
    sanitize_raw_data,
)


@pytest.mark.parametrize(
    "raw,expected_digits",
    [
        ("12345678", "12345678"),
        ("V12345678", "12345678"),
        ("V-12345678", "12345678"),
        ("12.345.678", "12345678"),
        ("C.I. 12345678", "12345678"),
        ("c.i.12345678", "12345678"),
    ],
)
def test_normalize_document_id_formats(raw: str, expected_digits: str) -> None:
    assert normalize_document_id(raw) == expected_digits
    assert document_id_last4(raw) == expected_digits[-4:]
    assert len(hash_document_id(raw)) == 64


def test_normalize_name_accents_and_enye() -> None:
    assert normalize_name("  José   María  Peña  ") == "jose maria pena"
    assert normalize_name("Niño Álvarez") == "nino alvarez"


def test_sanitize_raw_data_removes_full_document() -> None:
    raw = {
        "full_name": "Juan Pérez",
        "document_id": "12345678",
        "status": "missing",
    }
    sanitized = sanitize_raw_data(raw)

    assert sanitized is not None
    assert "document_id" not in sanitized
    assert sanitized["document_id_last4"] == "5678"
    assert sanitized["full_name"] == "Juan Pérez"
    assert "12345678" not in str(sanitized)


def test_sanitize_raw_data_strips_multiple_document_keys() -> None:
    raw = {"cedula": "98765432", "documento": "11223344"}
    sanitized = sanitize_raw_data(raw)

    assert sanitized is not None
    assert "cedula" not in sanitized
    assert "documento" not in sanitized
    assert sanitized["document_id_last4"] in {"5432", "3344"}


def test_normalize_status_aliases() -> None:
    assert normalize_status("desaparecido") == "missing"
    assert normalize_status("encontrado") == "found"
    assert normalize_status("albergue") == "shelter"
    assert normalize_status("otro") == "unknown"
