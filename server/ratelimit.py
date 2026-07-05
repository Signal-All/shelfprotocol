"""
In-memory per-IP rate limiter for the OpenShelf Registry.
Fixed one-minute windows, no external dependencies. Good enough for a single
process; swap for a Redis-backed limiter when the registry runs on more than
one box — the interface stays the same.
"""

from __future__ import annotations

import os
import threading
import time

# Set OPENSHELF_RATE_LIMIT=off to disable entirely (tests, local demos).
ENABLED = os.environ.get("OPENSHELF_RATE_LIMIT", "on").lower() not in ("off", "0", "false")

# Reads = GET (lookup, search, stats). Writes = POST (register, verify).
READS_PER_MIN = int(os.environ.get("OPENSHELF_RATE_LIMIT_READS_PER_MIN", "120"))
WRITES_PER_MIN = int(os.environ.get("OPENSHELF_RATE_LIMIT_WRITES_PER_MIN", "10"))

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, int], int] = {}
        self._current_window = 0

    def check(self, client_ip: str, kind: str, limit: int) -> tuple[bool, int]:
        """Count one request. Returns (allowed, seconds_until_window_resets)."""
        now = time.time()
        window = int(now // WINDOW_SECONDS)
        retry_after = WINDOW_SECONDS - int(now % WINDOW_SECONDS)
        key = (client_ip, kind, window)
        with self._lock:
            if window != self._current_window:
                # New window: drop every stale bucket so memory stays bounded.
                self._counts = {k: v for k, v in self._counts.items() if k[2] == window}
                self._current_window = window
            count = self._counts.get(key, 0) + 1
            self._counts[key] = count
        return count <= limit, retry_after
