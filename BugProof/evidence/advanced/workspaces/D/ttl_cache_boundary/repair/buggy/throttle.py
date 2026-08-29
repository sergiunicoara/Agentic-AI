class RequestThrottle:
    """Blocks a client from repeating a request until the cooldown window has fully elapsed."""

    def __init__(self, window_seconds, clock=None):
        self.window_seconds = window_seconds
        self._clock = clock or (lambda: 0)
        self._last_seen = {}

    def mark_request(self, client_id):
        self._last_seen[client_id] = self._clock()

    def is_throttled(self, client_id):
        """Return True if the client must still wait before making another request."""
        if client_id not in self._last_seen:
            return False
        elapsed = self._clock() - self._last_seen[client_id]
        return elapsed < self.window_seconds
