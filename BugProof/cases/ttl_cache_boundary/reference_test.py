from throttle import RequestThrottle


def test_client_is_still_blocked_exactly_at_the_window_boundary():
    now = {"t": 0}
    throttle = RequestThrottle(window_seconds=60, clock=lambda: now["t"])

    throttle.mark_request("client-1")
    now["t"] = 60

    assert throttle.is_throttled("client-1") is True
