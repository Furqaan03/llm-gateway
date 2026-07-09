# LLM Gateway — Rate Limiting, Fallback Routing & Observability

A production API gateway that sits in front of every LLM call an organization
makes. It normalizes requests across OpenAI, Anthropic, and Ollama; enforces
per-team rate limits and dollar budgets; automatically fails over to an
alternative provider when a primary is down or rate-limiting; and exports
unified Prometheus metrics for every interaction.

## Why this exists

Every company with more than one team using LLMs ends up building this — it's
pure infrastructure engineering applied to AI. It centralizes policy (limits,
budgets, allowed models, fallback) so individual teams don't each reinvent it.

## Architecture

```
src/providers/base.py           unified StandardRequest/StandardResponse across
                                 OpenAI/Anthropic/Ollama; classifies errors as
                                 retryable vs. permanent
src/limits/rate_limiter.py      token-bucket rate limiting, per team
src/limits/budget.py            monthly $ budgets with 80% warning + hard cap
src/resilience/circuit_breaker.py  closed/open/half-open breaker per provider-model
src/resilience/router.py        retry-with-backoff -> tier-based fallback chain,
                                 respecting circuit state
src/observability/metrics.py    Prometheus counters/histograms
src/config_loader.py            hot-reloadable per-team YAML config
src/api.py                      the gateway: auth -> rate limit -> budget ->
                                 resilient route -> metrics
config/teams.yaml               per-team keys, limits, budgets, allowed models
```

## Design decisions

- **Errors are classified retryable vs. permanent at the provider boundary.**
  A 429 or timeout is worth retrying/falling back; an auth failure or content-policy
  rejection is not — retrying those just wastes time and money. The router only
  burns retries on retryable errors, and falls back immediately on permanent ones.
- **Fallback chains are defined per *tier*, not per specific model.** If GPT-4o is
  down, the system routes to another high-tier model (Claude Sonnet), not to a
  random cheaper one — preserving the quality level the caller asked for. The
  system "always finds an available option" within the tier.
- **Circuit breaker per provider-model, with half-open probing.** After N
  failures the circuit opens and the gateway stops sending to that model entirely
  (fast-failing to fallback instead of timing out repeatedly). After a cooldown it
  allows a single probe; success closes it, failure re-opens it.
- **Time is injected, not read from the clock inside the logic.** Rate limiter,
  budget, circuit breaker, and router all take a `now`/`now_fn` parameter. This
  makes every resilience behavior deterministically testable without `sleep()` —
  the test suite exercises circuit open/half-open/close and token-bucket refill by
  advancing a fake clock.
- **In-process fallbacks for Redis.** The token bucket works in-memory so the
  gateway (and the full test suite) runs without a Redis server; Redis is wired in
  docker-compose for the distributed/multi-replica path.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env      # fill in OPENAI_API_KEY / ANTHROPIC_API_KEY
uvicorn src.api:app --reload
```

## Example

```bash
curl -X POST localhost:8000/v1/completions \
  -H "x-api-key: alpha-key-123" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "prompt": "Hello"}'
# -> {"model_requested": "gpt-4o-mini", "model_served": "...", "fell_back": false, "cost_usd": ...}

curl localhost:8000/admin/teams/team-alpha/status    # budget state
curl localhost:8000/metrics                          # Prometheus metrics
```

## Tests

```bash
pytest tests/ -v
```

15 tests covering token-bucket refill and per-team isolation, budget
ok/warning/blocked transitions, circuit breaker open/half-open/close/reopen, and
router fallback (primary-down, non-retryable-skips-retries, all-exhausted) — all
fully offline via injected clocks and a monkeypatched dispatch, no API key or
Redis required.

## Docker

```bash
docker compose up --build   # gateway + Redis + Prometheus + Grafana
```

## Status

Phases 1-4 complete (provider abstraction, rate limiting + budgets, resilience
with fallback + circuit breakers, Prometheus observability). Phase 5's dedicated
load test and pre-built Grafana dashboards are scaffolded (compose brings up
Prometheus/Grafana) but the dashboards are not yet checked in as JSON.
