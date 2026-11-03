"""Anthropic Server-Sent Events (SSE) formatters."""

import json
from typing import Any, Dict


def format_sse(event_type: str, data: Dict[str, Any]) -> str:
    """Format an Anthropic SSE event string with event and data lines."""
    json_str = json.dumps(data, separators=(",", ":"))
    return f"event: {event_type}\ndata: {json_str}\n\n"


def message_start_event(
    message_id: str,
    model: str,
    input_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> str:
    """Build message_start SSE event."""
    data = {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": max(0, input_tokens - cache_read_tokens),
                "output_tokens": 0,
                "cache_read_input_tokens": cache_read_tokens,
                "cache_creation_input_tokens": 0,
            },
        },
    }
    return format_sse("message_start", data)


def content_block_start_event(index: int, content_block: Dict[str, Any]) -> str:
    """Build content_block_start SSE event."""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": content_block,
    }
    return format_sse("content_block_start", data)


def content_block_delta_event(index: int, delta: Dict[str, Any]) -> str:
    """Build content_block_delta SSE event."""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": delta,
    }
    return format_sse("content_block_delta", data)


def content_block_stop_event(index: int) -> str:
    """Build content_block_stop SSE event."""
    data = {
        "type": "content_block_stop",
        "index": index,
    }
    return format_sse("content_block_stop", data)


def message_delta_event(
    stop_reason: str = "end_turn",
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> str:
    """Build message_delta SSE event."""
    data = {
        "type": "message_delta",
        "delta": {
            "stop_reason": stop_reason,
            "stop_sequence": None,
        },
        "usage": {
            "output_tokens": outputTokens if "outputTokens" in locals() else output_tokens,
            "cache_read_input_tokens": cache_read_tokens,
            "cache_creation_input_tokens": 0,
        },
    }
    return format_sse("message_delta", data)


def message_stop_event() -> str:
    """Build message_stop SSE event."""
    return format_sse("message_stop", {"type": "message_stop"})


def ping_event() -> str:
    """Build ping keep-alive SSE event."""
    return format_sse("ping", {"type": "ping"})
