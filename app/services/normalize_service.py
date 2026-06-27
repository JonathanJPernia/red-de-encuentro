import hashlib
import re
import unicodedata

VALID_APPEARANCE_STATUSES = frozenset({"missing", "found", "hospital", "shelter", "unknown"})

STATUS_ALIASES = {
    "desaparecido": "missing",
    "desaparecida": "missing",
    "missing": "missing",
    "encontrado": "found",
    "encontrada": "found",
    "found": "found",
    "hospital": "hospital",
    "hospitalizado": "hospital",
    "hospitalizada": "hospital",
    "refugio": "shelter",
    "albergue": "shelter",
    "shelter": "shelter",
    "unknown": "unknown",
    "desconocido": "unknown",
    "desconocida": "unknown",
}

DOCUMENT_RAW_DATA_KEYS = frozenset(
    {
        "document_id",
        "document",
        "documento",
        "cedula",
        "cédula",
        "ci",
        "c.i.",
        "c.i",
        "id_number",
        "numero_documento",
        "nro_documento",
        "dni",
        "rif",
        "identification",
        "identificacion",
    }
)

SENSITIVE_RAW_DATA_KEYS = DOCUMENT_RAW_DATA_KEYS | frozenset(
    {
        "contact",
        "telefono",
        "phone",
        "reportado_por_telefono",
        "reportado_por_nombre",
        "loc",
        "latitud",
        "longitud",
        "lat",
        "lng",
        "direccion_exacta",
        "direccion",
        "address",
        "coordinates",
        "ubicacion",
    }
)

DOCUMENT_TEXT_PATTERNS = (
    re.compile(r"(?i)c\.?\s*i\.?\s*:?\s*v?[\s\-.]*([\d.]+)"),
    re.compile(r"(?i)\(CI:\s*v?[\s\-.]*([\d.]+)\)"),
    re.compile(r"(?i)c\.?\s*i\.?\s+([\d.]+)"),
)


def normalize_name(name: str) -> str:
    """Normaliza un nombre para comparación sin alterar el full_name original."""
    text = name.strip().lower()
    text = text.replace("ñ", "n").replace("ü", "u")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_document_id(document_id: str) -> str:
    """
    Extrae solo dígitos de formatos como:
    V12345678, V-12345678, 12.345.678, C.I. 12345678, 12345678
    """
    cleaned = document_id.strip()
    cleaned = re.sub(r"(?i)c\.?\s*i\.?", "", cleaned)
    cleaned = re.sub(r"(?i)^v[\s\-]*", "", cleaned)
    return re.sub(r"\D", "", cleaned)


def is_document_query(query: str) -> bool:
    """True si la consulta parece un documento y no un nombre."""
    stripped = query.strip()
    if not stripped:
        return False

    digits = normalize_document_id(stripped)
    if len(digits) < 4:
        return False

    if re.fullmatch(r"\d+", stripped):
        return True

    residual = stripped.lower()
    residual = re.sub(r"(?i)c\.?\s*i\.?", "", residual)
    residual = re.sub(r"(?i)^v[\s\-]*", "", residual)
    residual = re.sub(r"[\d.\s\-]", "", residual)
    return residual == ""


def hash_document_id(document_id: str) -> str:
    """Genera SHA-256 del documento normalizado. No almacena la cédula en texto plano."""
    normalized = normalize_document_id(document_id)
    if not normalized:
        raise ValueError("Documento inválido: no contiene dígitos")
    if len(normalized) < 4:
        raise ValueError("Documento inválido: debe tener al menos 4 dígitos")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def document_id_last4(document_id: str) -> str:
    """Retorna los últimos 4 dígitos del documento normalizado."""
    normalized = normalize_document_id(document_id)
    if len(normalized) < 4:
        raise ValueError("Documento inválido: debe tener al menos 4 dígitos")
    return normalized[-4:]


def normalize_status(status: str) -> str:
    """Normaliza status de Appearance a valores permitidos."""
    key = status.strip().lower()
    key = re.sub(r"\s+", " ", key)
    normalized = STATUS_ALIASES.get(key, key)
    if normalized not in VALID_APPEARANCE_STATUSES:
        return "unknown"
    return normalized


def extract_document_from_text(text: str) -> str | None:
    """Intenta extraer un documento desde texto libre (ej. 'Nombre (CI: V-11.144.145)')."""
    for pattern in DOCUMENT_TEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            digits = normalize_document_id(match.group(1))
            if len(digits) >= 4:
                return digits
    return None


def split_name_and_document(full_text: str) -> tuple[str, str | None]:
    """Separa nombre visible y documento embebido en paréntesis o texto libre."""
    document_id = extract_document_from_text(full_text)
    name = re.sub(r"(?i)\(CI:.*?\)", "", full_text).strip()
    name = re.sub(r"(?i)c\.?\s*i\.?\s*:?\s*v?[\s\-.]*[\d.]+", "", name).strip(" -")
    name = re.sub(r"\s+", " ", name).strip()
    return name or full_text.strip(), document_id


def sanitize_raw_data(raw_data: dict | None) -> dict | None:
    """Elimina cédula completa y campos sensibles de raw_data."""
    if not raw_data:
        return raw_data

    sanitized: dict = {}
    for key, value in raw_data.items():
        key_normalized = key.strip().lower().replace(" ", "_")
        if key_normalized in SENSITIVE_RAW_DATA_KEYS:
            if key_normalized in DOCUMENT_RAW_DATA_KEYS and value is not None and str(value).strip():
                try:
                    sanitized["document_id_last4"] = document_id_last4(str(value))
                except ValueError:
                    pass
            continue
        if isinstance(value, str):
            embedded = extract_document_from_text(value)
            if embedded:
                try:
                    sanitized.setdefault("document_id_last4", document_id_last4(embedded))
                except ValueError:
                    pass
                value = re.sub(r"(?i)c\.?\s*i\.?\s*:?\s*v?[\s\-.]*[\d.]+", "[redactado]", value)
                value = re.sub(r"(?i)\(CI:.*?\)", "", value).strip()
        sanitized[key] = value

    return sanitized
