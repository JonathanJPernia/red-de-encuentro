from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

SourceHealthStatus = Literal["healthy", "degraded", "disabled"]

DEGRADED_TTL_MINUTES: dict[str, int] = {
    "cloudflare_challenge": 15,
    "rate_limited": 10,
    "timeout": 2,
    "forbidden": 5,
}
DEFAULT_DEGRADED_TTL_MINUTES = 5


@dataclass
class SourceHealthState:
    source_name: str
    status: SourceHealthStatus = "healthy"
    reason: str | None = None
    degraded_until: datetime | None = None
    last_error: str | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0


_states: dict[str, SourceHealthState] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create(source_name: str) -> SourceHealthState:
    if source_name not in _states:
        _states[source_name] = SourceHealthState(source_name=source_name)
    return _states[source_name]


def _ttl_for_reason(reason: str | None) -> timedelta:
    minutes = DEGRADED_TTL_MINUTES.get(reason or "", DEFAULT_DEGRADED_TTL_MINUTES)
    return timedelta(minutes=minutes)


def _expire_if_needed(state: SourceHealthState) -> None:
    if state.status != "degraded":
        return
    if state.degraded_until is None:
        return
    if state.degraded_until <= _utcnow():
        state.status = "healthy"
        state.degraded_until = None


def record_success(source_name: str) -> None:
    state = _get_or_create(source_name)
    state.status = "healthy"
    state.reason = None
    state.degraded_until = None
    state.last_error = None
    state.consecutive_failures = 0
    state.last_success_at = _utcnow()


def record_failure(
    source_name: str,
    error: str,
    *,
    reason: str | None = None,
) -> None:
    state = _get_or_create(source_name)
    now = _utcnow()
    state.consecutive_failures += 1
    state.last_error = error
    state.last_failure_at = now
    state.status = "degraded"
    state.reason = reason or "unknown"
    state.degraded_until = now + _ttl_for_reason(state.reason)

    logger.warning(
        "Fuente %s marcada como degraded por %s hasta %s",
        source_name,
        state.reason,
        state.degraded_until.isoformat(),
    )


def should_skip(source_name: str) -> bool:
    state = _get_or_create(source_name)
    _expire_if_needed(state)
    if state.status != "degraded":
        return False
    if state.degraded_until and state.degraded_until > _utcnow():
        logger.info(
            "Saltando %s: degraded hasta %s",
            source_name,
            state.degraded_until.isoformat(),
        )
        return True
    return False


def get_status(source_name: str) -> dict[str, Any]:
    state = _get_or_create(source_name)
    _expire_if_needed(state)
    return _serialize_state(state)


def get_all_statuses() -> list[dict[str, Any]]:
    return [get_status(name) for name in sorted(_states.keys())]


def _serialize_state(state: SourceHealthState) -> dict[str, Any]:
    return {
        "source_name": state.source_name,
        "status": state.status,
        "reason": state.reason,
        "degraded_until": state.degraded_until,
        "last_error": state.last_error,
        "last_success_at": state.last_success_at,
        "last_failure_at": state.last_failure_at,
        "consecutive_failures": state.consecutive_failures,
    }


def reset_all() -> None:
    """Solo para tests."""
    _states.clear()
