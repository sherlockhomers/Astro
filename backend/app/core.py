"""Shared retry configuration using Tenacity — imported by all external HTTP services."""
from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ── Standard HTTP retry config ─────────────────────────────────────────────
# Exponential back-off: 1s, 2s, 4s, 8s, 16s (max 5 attempts)
# Retries on common transient HTTP errors.
HTTP_RETRY = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=16.0),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True,
)

# More aggressive for reads (GET) that can tolerate stale data
GET_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
    reraise=True,
)
