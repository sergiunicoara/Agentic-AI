from throttle import RequestThrottle


def test_still_throttled_exactly_at_window_boundary():
    """The docstring promises a client is blocked "until the cooldown
    window has fully elapsed". That means the window must fully pass --
    strictly more time than window_seconds -- before a repeat request is
    allowed; at the exact instant elapsed == window_seconds, the client
    should still be throttled for "another moment".

    Support saw clients slip through right around the edge of the
    cooldown, which is exactly what happens when elapsed lands exactly on
    the boundary: the real-clock version of this is timing-dependent and
    hard to hit by hand, but a fake clock lets us land on the boundary
    deterministically.
    """
    current_time = [0]
    clock = lambda: current_time[0]

    throttle = RequestThrottle(window_seconds=10, clock=clock)
    throttle.mark_request("client-1")

    # Advance the clock to exactly the edge of the cooldown window --
    # not one moment past it.
    current_time[0] = 10

    assert throttle.is_throttled("client-1") is True, (
        "client should still be throttled exactly at the window boundary, "
        "since the window has not yet *fully* elapsed"
    )
