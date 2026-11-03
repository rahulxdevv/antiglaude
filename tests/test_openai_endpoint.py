"""Tests for OpenAI-compatible chat completions endpoint."""

import pytest
from fastapi.testclient import TestClient
from gateway.server import app

client = TestClient(app)


def test_openai_chat_completions_basic():
    """Test non-streaming OpenAI chat completion."""
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Return the exact word: BANANA"}
        ],
        "temperature": 0.0,
        "stream": False,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert "id" in data
    assert len(data["choices"]) > 0
    choice = data["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert "BANANA" in choice["message"]["content"].upper()
    assert data["usage"]["total_tokens"] > 0


def test_openai_chat_completions_streaming():
    """Test streaming OpenAI chat completion chunks."""
    payload = {
        "model": "gemini-3-flash",
        "messages": [
            {"role": "user", "content": "Count to 3"}
        ],
        "stream": True,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    body = response.text
    assert "chat.completion.chunk" in body
    assert "[DONE]" in body
