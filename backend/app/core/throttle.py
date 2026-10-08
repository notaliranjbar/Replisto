"""Small in-memory rate limits (wrong passwords, SMS codes, verification emails).

Kept in the API process: enough for one server running one API process, which is how we
deploy. Counters are lost on restart, which only ever makes them more lenient.
"""

import time
from collections import deque


class Throttle:
    """At most `limit` events per key within `window_seconds`."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        events = self._events.get(key)
        if events is None:
            return deque()
        cutoff = time.monotonic() - self.window
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            del self._events[key]
        return events

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.limit

    def retry_after(self, key: str) -> int:
        """Seconds until one more event is allowed (0 if it is now)."""
        events = self._recent(key)
        if len(events) < self.limit:
            return 0
        return max(1, int(events[0] + self.window - time.monotonic()) + 1)

    def hit(self, key: str) -> None:
        self._recent(key)
        self._events.setdefault(key, deque()).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._events.pop(key, None)

    def clear(self) -> None:
        self._events.clear()


def minutes_text(seconds: int) -> str:
    """'3 minutes' style wait time for messages (at least one minute)."""
    minutes = max(1, (seconds + 59) // 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"
