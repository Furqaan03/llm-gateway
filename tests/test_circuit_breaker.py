from src.resilience.circuit_breaker import CircuitBreaker


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, cooldown_sec=30)
    now = 100.0
    for _ in range(3):
        cb.record_failure(now)
    assert cb.state == cb.OPEN
    assert cb.allow_request(now) is False


def test_half_opens_after_cooldown():
    cb = CircuitBreaker(failure_threshold=2, cooldown_sec=30)
    now = 100.0
    cb.record_failure(now)
    cb.record_failure(now)
    assert cb.allow_request(now) is False           # still open during cooldown
    assert cb.allow_request(now + 31) is True        # cooldown elapsed -> half-open probe
    assert cb.state == cb.HALF_OPEN


def test_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=2, cooldown_sec=30)
    now = 100.0
    cb.record_failure(now)
    cb.record_failure(now)
    cb.allow_request(now + 31)  # -> half open
    cb.record_success()
    assert cb.state == cb.CLOSED
    assert cb.allow_request(now + 31) is True


def test_failure_in_half_open_reopens():
    cb = CircuitBreaker(failure_threshold=2, cooldown_sec=30)
    now = 100.0
    cb.record_failure(now)
    cb.record_failure(now)
    cb.allow_request(now + 31)  # half-open
    cb.record_failure(now + 31)
    assert cb.state == cb.OPEN
