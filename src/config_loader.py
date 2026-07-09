"""Loads per-team config from YAML and wires up limiters/budgets. Hot-reloadable."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from src.limits.budget import BudgetTracker
from src.limits.rate_limiter import RateLimiter

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "teams.yaml"


class TeamConfig(BaseModel):
    api_key: str
    requests_per_min: float
    monthly_budget_usd: float
    allowed_models: list[str]


class GatewayConfig:
    def __init__(self):
        self.teams: dict[str, TeamConfig] = {}
        self.api_key_to_team: dict[str, str] = {}
        self.rate_limiter = RateLimiter()
        self.budget = BudgetTracker()

    def load(self, path: Path = CONFIG_PATH) -> None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.teams.clear()
        self.api_key_to_team.clear()
        for team_id, cfg in data.get("teams", {}).items():
            tc = TeamConfig(**cfg)
            self.teams[team_id] = tc
            self.api_key_to_team[tc.api_key] = team_id
            self.rate_limiter.configure(team_id, tc.requests_per_min)
            self.budget.configure(team_id, tc.monthly_budget_usd)

    def resolve_team(self, api_key: str) -> str | None:
        return self.api_key_to_team.get(api_key)
