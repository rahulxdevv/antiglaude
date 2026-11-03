"""Tests for request converter and identity scrubbing."""

import pytest
from gateway.protocol.anthropic_models import AnthropicMessagesRequest, Message, ToolDefinition
from gateway.translation.request_converter import convert_anthropic_to_cloudcode, map_model_name
from gateway.translation.scrub import scrub_client_identity, strip_billing_header


def test_strip_billing_header():
    raw = "x-anthropic-billing-header: cc_version=2.1.274; cc_entrypoint=cli;\nYou are an assistant."
    cleaned = strip_billing_header(raw)
    assert "x-anthropic-billing-header" not in cleaned
    assert "You are an assistant." in cleaned


def test_scrub_client_identity():
    prompt = "You are Claude Code, created by Anthropic."
    scrubbed = scrub_client_identity(prompt)
    assert "Claude Code" not in scrubbed
    assert "Anthropic" not in scrubbed
    assert "the assistant" in scrubbed


def test_map_model_name():
    m, f = map_model_name("claude-3-7-sonnet-20250219")
    assert m == "claude-sonnet-4-6"
    assert f == "claude"

    m2, f2 = map_model_name("gemini-3-flash")
    assert m2 == "gemini-3-flash"
    assert f2 == "gemini"


def test_convert_anthropic_to_cloudcode_basic():
    req = AnthropicMessagesRequest(
        model="claude-3-7-sonnet-20250219",
        messages=[
            Message(role="user", content="Hello world"),
        ],
        system="You are an assistant.",
        max_tokens=1000,
    )
    payload = convert_anthropic_to_cloudcode(req, project_id="test-proj", account_email="user@test.com")
    assert payload["project"] == "test-proj"
    assert payload["model"] == "claude-sonnet-4-6"
    assert "request" in payload
    contents = payload["request"]["contents"]
    assert len(contents) == 1
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Hello world"


def test_convert_anthropic_to_cloudcode_with_tools():
    req = AnthropicMessagesRequest(
        model="claude-sonnet-4-6",
        messages=[
            Message(role="user", content="Run a command"),
        ],
        tools=[
            ToolDefinition(
                name="Bash",
                description="Run shell commands",
                input_schema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            )
        ],
    )
    payload = convert_anthropic_to_cloudcode(req, project_id="test-proj", account_email="user@test.com")
    tools = payload["request"].get("tools")
    assert tools is not None
    decls = tools[0]["functionDeclarations"]
    assert len(decls) == 1
    assert decls[0]["parameters"]["type"] == "OBJECT"
    assert "command" in decls[0]["parameters"]["properties"]

