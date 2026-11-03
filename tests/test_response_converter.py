"""Tests for response converter and SSE stream parsing."""

import json
import pytest
from gateway.translation.response_converter import StreamParser


def test_stream_parser_text_stream():
    parser = StreamParser(requested_model="claude-sonnet-4-6")

    chunk1 = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Hello "}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 25,
                "candidatesTokenCount": 2,
            },
        }
    }
    line1 = f"data: {json.dumps(chunk1)}"
    events1 = parser.parse_chunk(line1)
    assert len(events1) >= 2
    # Should include message_start, content_block_start, content_block_delta
    assert any("event: message_start" in ev for ev in events1)
    assert any("event: content_block_start" in ev for ev in events1)
    assert any("event: content_block_delta" in ev for ev in events1)

    chunk2 = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "world!"}]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "candidatesTokenCount": 4,
            },
        }
    }
    line2 = f"data: {json.dumps(chunk2)}"
    events2 = parser.parse_chunk(line2)
    assert any("world!" in ev for ev in events2)

    final_events = parser.finalize()
    assert any("event: content_block_stop" in ev for ev in final_events)
    assert any("event: message_delta" in ev for ev in final_events)
    assert any("event: message_stop" in ev for ev in final_events)


def test_stream_parser_tool_use():
    parser = StreamParser(requested_model="claude-sonnet-4-6")

    chunk = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "Bash",
                                    "args": {"command": "ls -la"},
                                    "id": "toolu_12345",
                                }
                            }
                        ]
                    }
                }
            ]
        }
    }
    line = f"data: {json.dumps(chunk)}"
    events = parser.parse_chunk(line)
    assert any("toolu_12345" in ev for ev in events)
    assert any("input_json_delta" in ev for ev in events)
    assert parser.stop_reason == "tool_use"
