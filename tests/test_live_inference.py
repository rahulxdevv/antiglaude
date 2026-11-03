"""Live integration test against Google Cloud Code backend."""

import pytest
from fastapi.testclient import TestClient
from gateway.server import app

client = TestClient(app)


def test_live_non_streaming_inference():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "Return exactly the word: PONG"}
        ],
        "max_tokens": 100,
        "stream": False,
    }
    response = client.post("/v1/messages", json=payload, timeout=25.0)
    assert response.status_code == 200, f"Error: {response.text}"
    data = response.json()
    assert data["role"] == "assistant"
    assert len(data["content"]) > 0
    # Content must contain text block
    text_blocks = [c for c in data["content"] if c.get("type") == "text"]
    assert len(text_blocks) > 0
    full_text = "".join(b.get("text", "") for b in text_blocks)
    assert "PONG" in full_text.upper()


def test_live_streaming_inference():
    payload = {
        "model": "gemini-3-flash",
        "messages": [
            {"role": "user", "content": "Say hello in exactly 2 words"}
        ],
        "max_tokens": 100,
        "stream": True,
    }
    response = client.post("/v1/messages", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    body = response.text
    assert "event: message_start" in body
    assert "event: content_block_delta" in body
    assert "event: message_delta" in body
    assert "event: message_stop" in body


def test_live_tool_calling():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "Use the calculate tool to add 123 and 456"}
        ],
        "tools": [
            {
                "name": "calculate",
                "description": "Calculate math expression",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            }
        ],
        "max_tokens": 200,
        "stream": True,
    }
    response = client.post("/v1/messages", json=payload)
    assert response.status_code == 200
    body = response.text
    assert "event: content_block_start" in body
    assert "tool_use" in body
    assert "calculate" in body
    assert "event: message_delta" in body
    assert "tool_use" in body

