"""Resilient routing: retry-with-backoff on the primary, then fall back down a
tier chain, respecting circuit breaker state per provider-model."""
from __future__ import annotations

import time

from src.providers.base import ProviderError, StandardRequest, StandardResponse, dispatch
from src.resilience.circuit_breaker import CircuitBreaker

# Fallback chains by tier: if the requested model is unavailable, try equivalents.
FALLBACK_CHAINS = {
    "high": ["gpt-4o", "claude-sonnet-4-5"],
    "medium": ["gpt-4o-mini", "claude-haiku-4-5", "llama3"],
    "low": ["llama3", "gpt-4o-mini"],
}

MODEL_TIER = {
    "gpt-4o": "high", "claude-sonnet-4-5": "high",
    "gpt-4o-mini": "medium", "claude-haiku-4-5": "medium",
    "llama3": "low",
}


class ResilientRouter:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._breakers: dict[str, CircuitBreaker] = {}

    def _breaker(self, model: str) -> CircuitBreaker:
        if model not in self._breakers:
            self._breakers[model] = CircuitBreaker()
        return self._breakers[model]

    def _try_model(self, req: StandardRequest, now_fn) -> StandardResponse | None:
        breaker = self._breaker(req.model)
        if not breaker.allow_request(now_fn()):
            return None  # circuit open, skip this model entirely

        for attempt in range(self.max_retries):
            try:
                resp = dispatch(req)
                breaker.record_success()
                return resp
            except ProviderError as exc:
                breaker.record_failure(now_fn())
                if not exc.retryable:
                    return None  # permanent error (auth/policy) — don't retry, fall back
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt * 0.1, 2.0))  # exponential backoff
        return None

    def route(self, req: StandardRequest, now_fn=time.time) -> StandardResponse:
        """Tries the requested model (with retries), then walks the fallback chain
        for its tier. Raises if every option is exhausted."""
        tier = MODEL_TIER.get(req.model, "medium")
        candidates = [req.model] + [m for m in FALLBACK_CHAINS[tier] if m != req.model]

        for model in candidates:
            resp = self._try_model(req.model_copy(update={"model": model}), now_fn)
            if resp is not None:
                return resp

        raise ProviderError(f"All providers exhausted for tier '{tier}'", retryable=False)
