import random
import time
from typing import Callable

# Transient server-side error markers (Google API raises these as
# exceptions with .code or embeds them in the message).
_SERVER_ERRORS = ("UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED",
                  "SERVER_ERROR", "BAD_GATEWAY", "SERVICE_UNAVAILABLE",
                  "TIMEOUT")
_SERVER_CODES = {500, 502, 503, 504}


def is_rate_limit(exc: Exception) -> bool:
    """Detect Gemini API rate-limit / quota errors (HTTP 429)."""
    if getattr(exc, "code", None) == 429:
        return True
    return "RESOURCE_EXHAUSTED" in str(exc)


def is_transient(exc: Exception) -> bool:
    """Detect any retry-worthy transient failure: rate limits, 5xx
    server errors, and network hiccups. A single one of these mid-job
    used to kill a whole segment even though a retry seconds later
    would have succeeded."""
    if is_rate_limit(exc):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in _SERVER_CODES:
        return True
    message = str(exc).upper()
    return any(marker in message for marker in _SERVER_ERRORS)


def call_with_retry(fn: Callable, retries: int = 4, base_delay: float = 5.0,
                    max_delay: float = 60.0):
    """Call fn(), retrying on transient failures (rate limits, 5xx,
    network errors) with exponential backoff + jitter.

    Free-tier Gemini quotas reset per minute, so a short wait usually
    succeeds. Use it around every live API call to keep the pipeline
    resilient during demos.
    """
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc) or attempt == retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 2), max_delay)
            print(f"Transient API error ({type(exc).__name__}: {str(exc)[:120]}); "
                  f"retrying in {delay:.0f}s (attempt {attempt + 1}/{retries})")
            time.sleep(delay)
    raise RuntimeError("unreachable")