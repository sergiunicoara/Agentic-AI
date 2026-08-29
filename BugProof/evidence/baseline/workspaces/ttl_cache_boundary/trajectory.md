# Trajectory

Read `report.md`: support has seen clients repeat an action right at the
edge of the cooldown window when it should still have been blocked "for
another moment." It's intermittent and nobody could reliably reproduce it
by hand.

Read `buggy/throttle.py`. `RequestThrottle.is_throttled` computes
`elapsed = self._clock() - self._last_seen[client_id]` and returns
`elapsed < self.window_seconds`. The class docstring says it "blocks a
client from repeating a request until the cooldown window has fully
elapsed" -- i.e. the client should stay throttled through the exact
boundary instant (elapsed == window_seconds) and only be released once
elapsed *exceeds* the window. The current `<` comparison instead releases
the client exactly at `elapsed == window_seconds`, one instant too early.
With a real wall clock this only shows up when a request happens to land
almost exactly on the window edge -- rare and unrepeatable by hand, which
matches the "intermittent, hard to pin down" complaint in the report. With
a fake/controlled clock the same boundary can be hit deterministically.

Wrote `candidate_test.py` (in the working directory, importing
`from throttle import RequestThrottle` per the stated execution setup)
using a fake clock: it marks a request at t=0, advances the clock to
exactly t=10 with `window_seconds=10`, and asserts `is_throttled` is still
`True` at that exact boundary.

Verified per the allowed one-time check: copied `candidate_test.py` into
`buggy/`, ran `pytest candidate_test.py -v` from `buggy/`. The test
failed as expected -- `assert False is True`, because `is_throttled`
returned `False` at the boundary instead of `True` -- confirming it
reproduces the reported defect. Removed the temporary copy and the
`__pycache__`/`.pytest_cache` directories pytest created, leaving `buggy/`
containing only the original `throttle.py`, unmodified.
