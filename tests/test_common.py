from scrapers import _common


def test_rate_limiter_serializes_request_starts(monkeypatch):
    times = iter([0.0, 0.0, 0.5])
    sleeps = []
    monkeypatch.setattr(_common.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(_common.time, "sleep", sleeps.append)

    limiter = _common.RateLimiter(requests_per_second=2)
    limiter.wait()
    limiter.wait()

    assert sleeps == [0.5]
