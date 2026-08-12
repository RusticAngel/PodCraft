import random
import time
from typing import Callable


def is_rate_limit(exc: Exception) -> bool:
    """Detect Gemini API rate-limit / quota errors (HTTP 429)."""
    if getattr(exc, "code", None) == 429:
        return True
    return "RESOURCE_EXHAUSTED" in str(exc)


def call_with_retry(fn: Callable, retries: int = 4, base_delay: float = 5.0,
                    max_delay: float = 60.0):
    """Call fn(), retrying on rate limits with exponential backoff + jitter.

    Free-tier Gemini quotas reset per minute, so a short wait usually
    succeeds. Use it around every live API call to keep the pipeline
    resilient during demos.
    """
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            if not is_rate_limit(exc) or attempt == retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 2), max_delay)
            print(f"Rate limited; retrying in {delay:.0f}s (attempt {attempt + 1}/{retries})")
            time.sleep(delay)
    raise RuntimeError("unreachable")