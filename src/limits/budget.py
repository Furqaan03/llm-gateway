"""Per-team monthly budget tracking with an 80% warning band and a hard cap."""
from __future__ import annotations

import threading


class BudgetTracker:
    def __init__(self):
        self._limits: dict[str, float] = {}   # team_id -> monthly USD cap
        self._spent: dict[str, float] = {}     # team_id -> USD spent this period
        self._lock = threading.Lock()

    def configure(self, team_id: str, monthly_cap_usd: float) -> None:
        with self._lock:
            self._limits[team_id] = monthly_cap_usd
            self._spent.setdefault(team_id, 0.0)

    def record_spend(self, team_id: str, cost_usd: float) -> None:
        with self._lock:
            self._spent[team_id] = self._spent.get(team_id, 0.0) + cost_usd

    def status(self, team_id: str) -> dict:
        cap = self._limits.get(team_id)
        spent = self._spent.get(team_id, 0.0)
        if cap is None:
            return {"team_id": team_id, "cap": None, "spent": spent, "state": "unlimited"}
        ratio = spent / cap if cap > 0 else 1.0
        state = "blocked" if ratio >= 1.0 else ("warning" if ratio >= 0.8 else "ok")
        return {"team_id": team_id, "cap": cap, "spent": round(spent, 4), "ratio": round(ratio, 3), "state": state}

    def is_blocked(self, team_id: str) -> bool:
        return self.status(team_id)["state"] == "blocked"
