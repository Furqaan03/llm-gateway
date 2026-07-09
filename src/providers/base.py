"""Unified provider abstraction: normalize a standard request across all providers."""
from __future__ import annotations

import time

import httpx
from pydantic import BaseModel

# Per-1M-token pricing (USD), for cost tracking / budget enforcement.
PRICING = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "llama3": (0.0, 0.0),
}

# Fallback chains by tier: if a model is down, try the next equivalent.
MODEL_TO_PROVIDER = {
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "claude-sonnet-4-5": "anthropic",
    "claude-haiku-4-5": "anthropic",
    "llama3": "ollama",
}


class StandardRequest(BaseModel):
    model: str
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.0
    stream: bool = False


class StandardResponse(BaseModel):
    output_text: str
    model_served: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


class ProviderError(Exception):
    """Raised on a provider call failure. `retryable` distinguishes transient
    failures (429/timeout) from permanent ones (auth/content policy)."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _cost(model: str, in_tok: int, out_tok: int) -> float:
    inp, out = PRICING.get(model, (0.0, 0.0))
    return (in_tok / 1_000_000) * inp + (out_tok / 1_000_000) * out


def call_openai(req: StandardRequest) -> StandardResponse:
    from openai import OpenAI, APIError, RateLimitError

    start = time.perf_counter()
    try:
        resp = OpenAI().chat.completions.create(
            model=req.model,
            messages=[{"role": "user", "content": req.prompt}],
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
    except RateLimitError as exc:
        raise ProviderError(str(exc), retryable=True) from exc
    except APIError as exc:
        raise ProviderError(str(exc), retryable=getattr(exc, "status_code", 500) >= 500) from exc

    usage = resp.usage
    in_tok = usage.prompt_tokens if usage else 0
    out_tok = usage.completion_tokens if usage else 0
    return StandardResponse(
        output_text=resp.choices[0].message.content or "",
        model_served=req.model, provider="openai",
        input_tokens=in_tok, output_tokens=out_tok,
        latency_ms=(time.perf_counter() - start) * 1000,
        cost_usd=_cost(req.model, in_tok, out_tok),
    )


def call_anthropic(req: StandardRequest) -> StandardResponse:
    from anthropic import Anthropic, APIError, RateLimitError

    start = time.perf_counter()
    try:
        resp = Anthropic().messages.create(
            model=req.model, max_tokens=req.max_tokens,
            messages=[{"role": "user", "content": req.prompt}],
        )
    except RateLimitError as exc:
        raise ProviderError(str(exc), retryable=True) from exc
    except APIError as exc:
        raise ProviderError(str(exc), retryable=getattr(exc, "status_code", 500) >= 500) from exc

    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return StandardResponse(
        output_text=text, model_served=req.model, provider="anthropic",
        input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
        latency_ms=(time.perf_counter() - start) * 1000,
        cost_usd=_cost(req.model, resp.usage.input_tokens, resp.usage.output_tokens),
    )


def call_ollama(req: StandardRequest, base_url: str = "http://localhost:11434") -> StandardResponse:
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{base_url}/api/generate", json={"model": req.model, "prompt": req.prompt, "stream": False})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise ProviderError(str(exc), retryable=True) from exc

    return StandardResponse(
        output_text=data.get("response", ""), model_served=req.model, provider="ollama",
        input_tokens=data.get("prompt_eval_count", 0), output_tokens=data.get("eval_count", 0),
        latency_ms=(time.perf_counter() - start) * 1000, cost_usd=0.0,
    )


def dispatch(req: StandardRequest) -> StandardResponse:
    provider = MODEL_TO_PROVIDER.get(req.model)
    if provider == "openai":
        return call_openai(req)
    if provider == "anthropic":
        return call_anthropic(req)
    if provider == "ollama":
        return call_ollama(req)
    raise ProviderError(f"Unknown model '{req.model}'", retryable=False)
