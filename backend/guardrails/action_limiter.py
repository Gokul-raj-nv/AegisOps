"""Action limiter — rate-limits and tracks automated remediation actions.

Prevents the system from executing the same action repeatedly in a short
window (e.g., restarting a service 5 times in 10 minutes).
Uses an in-process sliding window counter — replace with Redis in production.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


# Action limits: (max_count, window_seconds)
_ACTION_LIMITS: dict[str, tuple[int, int]] = {
    "restart_service": (2, 600),              # max 2 restarts per 10 min
    "increase_db_pool_size": (3, 3600),       # max 3 pool increases per hour
    "scale_service_replicas": (5, 3600),      # max 5 scale events per hour
    "terminate_long_queries": (2, 300),       # max 2 query kills per 5 min
    "_default": (10, 3600),                   # default: 10 per hour
}


@dataclass
class LimitCheckResult:
    allowed: bool
    action_id: str
    count_in_window: int
    max_allowed: int
    window_seconds: int
    reason: str


class ActionLimiter:
    """Thread-safe sliding-window rate limiter for remediation actions."""

    def __init__(self) -> None:
        # Maps action_id → deque of execution timestamps
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, action_id: str) -> LimitCheckResult:
        """Check if an action is within its rate limit."""
        max_count, window_sec = _ACTION_LIMITS.get(
            action_id, _ACTION_LIMITS["_default"]
        )
        now = time.time()
        cutoff = now - window_sec

        with self._lock:
            history = self._history[action_id]
            # Evict old entries
            while history and history[0] < cutoff:
                history.popleft()
            count = len(history)

        allowed = count < max_count
        return LimitCheckResult(
            allowed=allowed,
            action_id=action_id,
            count_in_window=count,
            max_allowed=max_count,
            window_seconds=window_sec,
            reason=(
                f"Action '{action_id}': {count}/{max_count} executions in last {window_sec}s. "
                f"{'ALLOWED' if allowed else 'RATE LIMITED'}."
            ),
        )

    def record(self, action_id: str) -> None:
        """Record that an action was executed."""
        with self._lock:
            self._history[action_id].append(time.time())

    def check_and_record(self, action_id: str) -> LimitCheckResult:
        """Atomically check the limit and record if allowed."""
        result = self.check(action_id)
        if result.allowed:
            self.record(action_id)
        return result


# Module-level singleton
_limiter = ActionLimiter()


def check_action_limit(action_id: str) -> LimitCheckResult:
    """Check if an action is within its rate limit (module-level)."""
    return _limiter.check(action_id)


def record_action_executed(action_id: str) -> None:
    """Record that an action was executed (module-level)."""
    _limiter.record(action_id)
