"""In-memory per-client rate limiting for chat messages."""

import math
import os
import time
from collections import deque
from dataclasses import dataclass


DEFAULT_MAX_MESSAGES = 5
DEFAULT_WINDOW_SECONDS = 10.0


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class AntiBotService:
    def __init__(self, max_messages=None, window_seconds=None):
        self.max_messages = (
            int(os.getenv("ANTIBOT_MAX_MESSAGES", DEFAULT_MAX_MESSAGES))
            if max_messages is None
            else max_messages
        )
        self.window_seconds = (
            float(os.getenv("ANTIBOT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS))
            if window_seconds is None
            else window_seconds
        )
        if self.max_messages < 1:
            raise ValueError("max_messages must be at least 1")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self._message_times = {}

    def check_message(self, client, now=None):
        """Allow at most max_messages for a client in the active time window."""
        current_time = time.monotonic() if now is None else float(now)
        cutoff = current_time - self.window_seconds
        message_times = self._message_times.setdefault(client, deque())

        while message_times and message_times[0] <= cutoff:
            message_times.popleft()

        if len(message_times) >= self.max_messages:
            retry_after = self.window_seconds - (current_time - message_times[0])
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=max(1, math.ceil(retry_after)),
            )

        message_times.append(current_time)
        return RateLimitDecision(allowed=True)

    def remove_client(self, client):
        self._message_times.pop(client, None)

    def clear(self):
        self._message_times.clear()
