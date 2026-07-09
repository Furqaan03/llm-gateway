"""Prometheus metrics for the gateway."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUESTS = Counter("gateway_requests_total", "Total requests", ["team", "model", "provider", "status"])
FALLBACKS = Counter("gateway_fallback_total", "Fallback activations", ["requested_model", "served_model"])
TOKENS = Counter("gateway_tokens_total", "Tokens processed", ["team", "direction"])
COST = Counter("gateway_cost_usd_total", "Cost in USD", ["team"])
LATENCY = Histogram("gateway_latency_seconds", "Request latency", ["provider"])
RATE_LIMITED = Counter("gateway_rate_limited_total", "Rate-limited requests", ["team"])
BUDGET_BLOCKED = Counter("gateway_budget_blocked_total", "Budget-blocked requests", ["team"])
