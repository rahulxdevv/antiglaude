"""Tests for OpenAI-compatible chat completions endpoint."""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from gateway.protocol.anthropic_models import (
    AnthropicMessagesResponse,
    TextContentBlock,
    UsageMetadata,
)
from gateway.server import app

client = TestClient(app)


def test_openai_chat_completions_basic():
    """Test non-streaming OpenAI chat completion."""
    mock_resp = AnthropicMessagesResponse(
        id="msg_mock_123",
        model="claude-sonnet-4-6",
        content=[TextContentBlock(text="Here is your BANANA.")],
        usage=UsageMetadata(input_tokens=15, output_tokens=8),
    )

    with patch(
        "gateway.server.cloudcode_provider.complete_messages",
        new=AsyncMock(return_value=mock_resp),
    ):
        payload = {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Return the exact word: BANANA"},
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
        assert data["usage"]["total_tokens"] == 23


def test_openai_chat_completions_streaming():
    """Test streaming OpenAI chat completion chunks."""
    async def mock_stream(*args, **kwargs):
        yield 'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1","model":"claude-sonnet-4-6","usage":{"input_tokens":5}}}\n\n'
        yield 'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        yield 'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"1, 2, 3"}}\n\n'
        yield 'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
        yield 'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}\n\n'
        yield 'event: message_stop\ndata: {"type":"message_stop"}\n\n'

    with patch(
        "gateway.server.cloudcode_provider.stream_messages",
        side_effect=mock_stream,
    ):
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
