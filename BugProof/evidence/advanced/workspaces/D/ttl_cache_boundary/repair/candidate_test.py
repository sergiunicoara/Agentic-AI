"""
Reproduces the bug from report.md: a client can repeat an action exactly at
the boundary of the cooldown window, when the throttle should still be
blocking it for that instant.

RequestThrottle.is_throttled() uses `elapsed < self.window_seconds` to decide
whether a client is still blocked. This means that once elapsed time reaches
*exactly* window_seconds, is_throttled() returns False (not throttled) --
letting the client through at the very edge of the cooldown window, rather
than only after the window has strictly passed. This matches the report's
description of clients getting through "right around the edge of the
cooldown window, when it should have still been blocked for another moment".
"""

from throttle import RequestThrottle


def test_client_still_blocked_exactly_at_window_boundary():
    # Fake clock: first call (during mark_request) returns 0, second call
    # (during is_throttled) returns exactly window_seconds later.
    times = iter([0, 10])
    clock = lambda: next(times)

    throttle = RequestThrottle(window_seconds=10, clock=clock)
    throttle.mark_request("client-1")

    # Exactly window_seconds has elapsed -- the cooldown window has not yet
    # been left behind, only just reached, so the client should still be
    # blocked for that instant. is_throttled()'s own docstring in
    # buggy/throttle.py defines what a truthy result means here: "Return
    # True if the client must still wait before making another request."
    # We assert truthiness (not an exact `is True` identity check) since
    # that docstring establishes the *meaning* of a truthy return, not a
    # literal True value pinned by the report.
    assert throttle.is_throttled("client-1")
