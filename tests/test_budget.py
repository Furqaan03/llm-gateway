from src.limits.budget import BudgetTracker


def test_states_transition_with_spend():
    b = BudgetTracker()
    b.configure("team-a", monthly_cap_usd=100.0)
    assert b.status("team-a")["state"] == "ok"
    b.record_spend("team-a", 85.0)
    assert b.status("team-a")["state"] == "warning"
    b.record_spend("team-a", 20.0)
    assert b.status("team-a")["state"] == "blocked"
    assert b.is_blocked("team-a")


def test_unconfigured_team_is_unlimited():
    b = BudgetTracker()
    assert b.status("ghost")["state"] == "unlimited"
    assert b.is_blocked("ghost") is False
