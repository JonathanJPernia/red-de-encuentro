import time
from collections import defaultdict


class InMemoryRateLimiter:
    """Rate limiter simple en memoria por clave (ej. user_id de Telegram)."""

    def __init__(self, max_calls: int, period_seconds: int) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        hits = [timestamp for timestamp in self._hits[key] if now - timestamp < self.period_seconds]

        if len(hits) >= self.max_calls:
            self._hits[key] = hits
            return False

        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
