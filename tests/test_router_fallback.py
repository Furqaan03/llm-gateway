import src.resilience.router as router_mod
from src.providers.base import ProviderError, StandardRequest, StandardResponse
from src.resilience.router import ResilientRouter


def _ok_response(model: str) -> StandardResponse:
    return StandardResponse(
        output_text="ok", model_served=model, provider="test",
        input_tokens=1, output_tokens=1, latency_ms=1.0, cost_usd=0.0,
    )


def test_falls_back_when_primary_fails(monkeypatch):
    calls = []

    def fake_dispatch(req: StandardRequest) -> StandardResponse:
        calls.append(req.model)
        if req.model == "gpt-4o":
            raise ProviderError("primary down", retryable=True)
        return _ok_response(req.model)

    monkeypatch.setattr(router_mod, "dispatch", fake_dispatch)
    r = ResilientRouter(max_retries=1)
    resp = r.route(StandardRequest(model="gpt-4o", prompt="hi"), now_fn=lambda: 0.0)
    assert resp.model_served == "claude-sonnet-4-5"  # fell back to the other high-tier model
    assert "gpt-4o" in calls


def test_non_retryable_error_skips_retries_and_falls_back(monkeypatch):
    attempts = {"gpt-4o": 0}

    def fake_dispatch(req: StandardRequest) -> StandardResponse:
        if req.model == "gpt-4o":
            attempts["gpt-4o"] += 1
            raise ProviderError("auth failure", retryable=False)
        return _ok_response(req.model)

    monkeypatch.setattr(router_mod, "dispatch", fake_dispatch)
    r = ResilientRouter(max_retries=3)
    resp = r.route(StandardRequest(model="gpt-4o", prompt="hi"), now_fn=lambda: 0.0)
    assert attempts["gpt-4o"] == 1   # non-retryable -> only tried once
    assert resp.model_served == "claude-sonnet-4-5"


def test_raises_when_all_exhausted(monkeypatch):
    def fake_dispatch(req: StandardRequest) -> StandardResponse:
        raise ProviderError("everything down", retryable=False)

    monkeypatch.setattr(router_mod, "dispatch", fake_dispatch)
    r = ResilientRouter(max_retries=1)
    try:
        r.route(StandardRequest(model="gpt-4o", prompt="hi"), now_fn=lambda: 0.0)
        assert False, "should have raised"
    except ProviderError:
        pass
