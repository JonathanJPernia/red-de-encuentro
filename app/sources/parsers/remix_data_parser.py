from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

PERSON_FIELD_KEYS = {
    "_52": "id",
    "_54": "firstName",
    "_56": "lastName",
    "_58": "idNumber",
    "_61": "gender",
    "_63": "age",
    "_65": "description",
    "_66": "status",
    "_68": "createdAt",
    "_70": "updatedAt",
    "_72": "lastActivityAt",
    "_75": "foundNote",
    "_76": "hospitalName",
    "_77": "hospitalStatus",
}

SKIPPED_PERSON_KEYS = frozenset({"_73", "_59"})


def parse_remix_root_data(raw_text: str) -> list[dict[str, Any]]:
    """
    Parsea respuestas de `/_root.data` (Remix/React Router serialized).

    Soporta JSON normal con data.persons o arrays serializados con referencias.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Venezuela Te Busca: JSON inválido en _root.data")
        return []

    if isinstance(payload, dict):
        persons = payload.get("data", {}).get("persons")
        return persons if isinstance(persons, list) else []

    if not isinstance(payload, list):
        return []

    persons_indices: list[int] | None = None
    for index, item in enumerate(payload):
        if item == "persons" and index + 1 < len(payload):
            candidate = payload[index + 1]
            if isinstance(candidate, list):
                persons_indices = candidate
            break

    if not persons_indices:
        return _fallback_extract_persons(payload)

    persons: list[dict[str, Any]] = []
    for person_index in persons_indices:
        if not isinstance(person_index, int) or person_index < 0 or person_index >= len(payload):
            continue
        raw_person = payload[person_index]
        if not isinstance(raw_person, dict):
            continue
        person = _extract_person_from_remix_dict(raw_person, payload)
        if person:
            persons.append(person)

    return persons


def _extract_person_from_remix_dict(raw_person: dict, arr: list[Any]) -> dict[str, Any] | None:
    person: dict[str, Any] = {}
    for remix_key, field_name in PERSON_FIELD_KEYS.items():
        if remix_key in SKIPPED_PERSON_KEYS or remix_key not in raw_person:
            continue
        value = _deref_leaf(raw_person[remix_key], arr)
        if value is not None and value != "":
            person[field_name] = value

    first = str(person.get("firstName") or "").strip()
    last = str(person.get("lastName") or "").strip()
    if not first and not last:
        return None

    return person


def _deref_leaf(index: Any, arr: list[Any]) -> Any:
    if not isinstance(index, int) or index < 0 or index >= len(arr):
        return None
    value = arr[index]
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


def _fallback_extract_persons(arr: list[Any]) -> list[dict[str, Any]]:
    """Fallback defensivo: busca dicts con claves firstName/lastName literales."""
    persons: list[dict[str, Any]] = []
    for item in arr:
        if isinstance(item, dict) and ("firstName" in item or "lastName" in item):
            persons.append(dict(item))
    return persons


def contains_contact_info(text: str) -> bool:
    if not text:
        return False
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        return True
    if re.search(r"\b\d{7,}\b", text):
        return True
    if re.search(r"\b0\d{3}[-\s]?\d{7}\b", text):
        return True
    return False
