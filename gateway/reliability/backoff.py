"""Exponential backoff and rate-limit parser utilities."""

import asyncio
import logging
import random
import re
from typing import Optional

logger = logging.getLogger("gateway.reliability")


def parse_retry_after(error_text: str, default_delay: float = 2.0) -> float:
    """Parse reset delay from error message or headers."""
    # Look for "reset after Xs" or "retry after X seconds"
    match = re.search(r"(?:reset after|retry in|retry after)\s*(\d+(?:\.\d+)?)\s*s", error_text, re.IGNORECASE)
    if match:
        return float(match.group(1))

    # Look for milliseconds
    match_ms = re.search(r"(\d+)\s*ms", error_text, re.IGNORECASE)
    if match_ms:
        return float(match_ms.group(1)) / 1000.0

    return default_delay


def calculate_backoff(attempt: int, base: float = 1.0, max_delay: float = 30.0) -> float:
    """Calculate exponential backoff with full jitter."""
    exp = min(max_delay, base * (2 ** attempt))
    # Full jitter: random uniform between 0 and exp
    jittered = random.uniform(exp * 0.5, exp)
    return jittered
