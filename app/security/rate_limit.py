"""Sliding-window rate limiter for authentication endpoints (brute force / credential stuffing).

# ponytail: in-process memory, correct for the single uvicorn worker GeoVault runs.
# Ceiling: limits are per-process and reset on restart. Move to a Postgres/Redis counter
# if the API ever runs with multiple workers or replicas.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and q[0] <= now - self.window:
            q.popleft()

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again; 0 if it is currently allowed."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            self._prune(q, now)
            if len(q) < self.limit:
                return 0
            return max(1, int(q[0] + self.window - now) + 1)

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            q.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


class LoginLimiter:
    """Failed logins are limited per account AND per client IP.

    Per-account stops guessing one victim's password from many IPs; per-IP stops one client
    spraying many accounts. Successful logins clear the account counter.
    """

    def __init__(self, per_account: int = 5, per_ip: int = 20, window_seconds: int = 900):
        self.account = RateLimiter(per_account, window_seconds)
        self.ip = RateLimiter(per_ip, window_seconds)

    def retry_after(self, email: str, ip: str) -> int:
        return max(self.account.retry_after(email.lower()), self.ip.retry_after(ip))

    def failed(self, email: str, ip: str) -> None:
        self.account.hit(email.lower())
        self.ip.hit(ip)

    def succeeded(self, email: str) -> None:
        self.account.reset(email.lower())
