"""Circuit breaker: after N failures in a window, open the circuit and stop
sending to a provider; after a cooldown, allow one test request (half-open)."""
from __future__ import annotations

import threading


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, cooldown_sec: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec
        self.state = self.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    def allow_request(self, now: float) -> bool:
        with self._lock:
            if self.state == self.OPEN:
                if self.opened_at is not None and (now - self.opened_at) >= self.cooldown_sec:
                    self.state = self.HALF_OPEN
                    return True  # one probe allowed
                return False
            return True  # closed or half-open both allow

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = self.CLOSED
            self.opened_at = None

    def record_failure(self, now: float) -> None:
        with self._lock:
            self.failure_count += 1
            if self.state == self.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                self.opened_at = now
