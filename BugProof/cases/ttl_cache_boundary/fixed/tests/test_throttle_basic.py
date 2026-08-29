from throttle import RequestThrottle


def test_client_not_seen_before_is_not_throttled():
    throttle = RequestThrottle(window_seconds=60, clock=lambda: 0)

    assert throttle.is_throttled("new-client") is False
