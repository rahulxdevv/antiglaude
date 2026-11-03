"""Scrubbing utilities for system prompts and headers to avoid Cloud Code 429 triggers."""

import re
from typing import Any, Dict, List, Union

from gateway.config import DEFAULT_CONFIG

BILLING_HEADER_REGEX = re.compile(r"^x-anthropic-billing-header:[^\n]*\n?", re.IGNORECASE | re.MULTILINE)


def strip_billing_header(text: str) -> str:
    """Strip x-anthropic-billing-header pseudo-header that triggers Cloud Code 429."""
    if not isinstance(text, str):
        return text
    return BILLING_HEADER_REGEX.sub("", text).strip()


def scrub_client_identity(text: str, rules: List[tuple] = None) -> str:
    """Scrub vendor identities in system prompts to prevent Cloud Code filter trips."""
    if not isinstance(text, str):
        return text

    if rules is None:
        rules = DEFAULT_CONFIG.scrub_rules

    out = text
    for pattern, replacement in rules:
        out = re.sub(pattern, replacement, out)
    return out


def clean_cache_control(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove cache_control metadata fields that Cloud Code rejects."""
    cleaned = []
    for msg in messages:
        m = dict(msg)
        m.pop("cache_control", None)
        content = m.get("content")
        if isinstance(content, list):
            cleaned_content = []
            for block in content:
                if isinstance(block, dict):
                    b = dict(block)
                    b.pop("cache_control", None)
                    cleaned_content.append(b)
                else:
                    cleaned_content.append(block)
            m["content"] = cleaned_content
        cleaned.append(m)
    return cleaned
