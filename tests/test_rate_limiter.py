from src.limits.rate_limiter import RateLimiter, TokenBucket


def test_bucket_allows_up_to_capacity_then_blocks():
    bucket = TokenBucket(rate_per_sec=1.0, capacity=5)
    now = 1000.0
    allowed = [bucket.try_consume(now) for _ in range(5)]
    assert all(allowed)
    assert bucket.try_consume(now) is False  # 6th in same instant -> blocked


def test_bucket_refills_over_time():
    bucket = TokenBucket(rate_per_sec=2.0, capacity=2)
    now = 1000.0
    assert bucket.try_consume(now)
    assert bucket.try_consume(now)
    assert bucket.try_consume(now) is False
    # 1 second later, 2 tokens refilled
    assert bucket.try_consume(now + 1.0)


def test_rate_limiter_per_team_isolation():
    rl = RateLimiter()
    rl.configure("team-a", requests_per_min=60)
    rl.configure("team-b", requests_per_min=60)
    now = 2000.0
    # exhaust team-a
    for _ in range(60):
        rl.allow("team-a", now)
    assert rl.allow("team-a", now) is False
    # team-b unaffected
    assert rl.allow("team-b", now) is True


def test_unconfigured_team_is_unlimited():
    rl = RateLimiter()
    assert rl.allow("nobody") is True
