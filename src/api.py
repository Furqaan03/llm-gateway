"""The gateway: auth -> rate limit -> budget -> resilient routing -> metrics."""
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from src.config_loader import GatewayConfig
from src.observability import metrics
from src.providers.base import ProviderError, StandardRequest
from src.resilience.router import ResilientRouter

load_dotenv()

app = FastAPI(title="LLM Gateway")
config = GatewayConfig()
router = ResilientRouter()


@app.on_event("startup")
def _startup() -> None:
    config.load()


class GatewayRequest(BaseModel):
    model: str
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.0


@app.post("/v1/completions")
def completions(req: GatewayRequest, x_api_key: str = Header(...)) -> dict:
    team_id = config.resolve_team(x_api_key)
    if team_id is None:
        raise HTTPException(401, "Invalid API key")

    team_cfg = config.teams[team_id]
    if req.model not in team_cfg.allowed_models:
        raise HTTPException(403, f"Team '{team_id}' is not allowed to use model '{req.model}'")

    if not config.rate_limiter.allow(team_id):
        metrics.RATE_LIMITED.labels(team=team_id).inc()
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "1"})

    if config.budget.is_blocked(team_id):
        metrics.BUDGET_BLOCKED.labels(team=team_id).inc()
        raise HTTPException(402, f"Team '{team_id}' has exhausted its budget")

    std_req = StandardRequest(model=req.model, prompt=req.prompt, max_tokens=req.max_tokens, temperature=req.temperature)
    try:
        resp = router.route(std_req)
    except ProviderError as exc:
        metrics.REQUESTS.labels(team=team_id, model=req.model, provider="none", status="error").inc()
        raise HTTPException(503, str(exc))

    if resp.model_served != req.model:
        metrics.FALLBACKS.labels(requested_model=req.model, served_model=resp.model_served).inc()

    config.budget.record_spend(team_id, resp.cost_usd)
    metrics.REQUESTS.labels(team=team_id, model=req.model, provider=resp.provider, status="ok").inc()
    metrics.TOKENS.labels(team=team_id, direction="input").inc(resp.input_tokens)
    metrics.TOKENS.labels(team=team_id, direction="output").inc(resp.output_tokens)
    metrics.COST.labels(team=team_id).inc(resp.cost_usd)
    metrics.LATENCY.labels(provider=resp.provider).observe(resp.latency_ms / 1000)

    return {
        "output_text": resp.output_text,
        "model_requested": req.model,
        "model_served": resp.model_served,
        "provider": resp.provider,
        "cost_usd": resp.cost_usd,
        "latency_ms": resp.latency_ms,
        "fell_back": resp.model_served != req.model,
    }


@app.get("/admin/teams/{team_id}/status")
def team_status(team_id: str) -> dict:
    if team_id not in config.teams:
        raise HTTPException(404, "Unknown team")
    return config.budget.status(team_id)


@app.post("/admin/reload")
def reload_config() -> dict:
    config.load()
    return {"status": "reloaded", "teams": list(config.teams.keys())}


@app.get("/metrics")
def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
