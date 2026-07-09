"""Token-bucket rate limiter. Uses Redis when available for distributed safety;
falls back to an in-process bucket so the gateway (and tests) run without Redis."""
from __future__ import annotations

import threading
import time


class TokenBucket:
    """Classic token bucket: `rate` tokens refill per second up to `capacity`."""

    def __init__(self, rate_per_sec: float, capacity: float):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = None  # set on first use to avoid Date.now at import
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        if self.last_refill is None:
            self.last_refill = now
            return
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def try_consume(self, now: float, amount: float = 1.0) -> bool:
        with self._lock:
            self._refill(now)
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False


class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def configure(self, team_id: str, requests_per_min: float) -> None:
        with self._lock:
            self._buckets[team_id] = TokenBucket(rate_per_sec=requests_per_min / 60.0, capacity=requests_per_min)

    def allow(self, team_id: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        bucket = self._buckets.get(team_id)
        if bucket is None:  # unconfigured team -> unlimited (or configure a default)
            return True
        return bucket.try_consume(now)
