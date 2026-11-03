"""Tests for schema_sanitizer."""

import pytest
from gateway.protocol.schema_sanitizer import sanitize_schema


def test_sanitize_schema_basic():
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "BashTool",
        "type": "object",
        "additionalProperties": False,
        "propertyNames": {"pattern": "^[a-z]+$"},
        "properties": {
            "command": {
                "type": "string",
                "description": "Command to run",
            }
        },
        "required": ["command"],
    }
    cleaned = sanitize_schema(schema)
    assert "$schema" not in cleaned
    assert "additionalProperties" not in cleaned
    assert "propertyNames" not in cleaned
    assert "title" not in cleaned
    assert cleaned["type"] == "OBJECT"
    assert "command" in cleaned["properties"]
    assert cleaned["properties"]["command"]["type"] == "STRING"
    assert cleaned["required"] == ["command"]


def test_sanitize_schema_flatten_anyof():
    schema = {
        "type": "object",
        "properties": {
            "target": {
                "anyOf": [
                    {"type": "string", "description": "file path"},
                    {"type": "null"},
                ]
            }
        },
    }
    cleaned = sanitize_schema(schema)
    assert "anyOf" not in cleaned["properties"]["target"]
    assert cleaned["properties"]["target"]["type"] == "STRING"
    assert cleaned["properties"]["target"]["description"] == "file path"


def test_sanitize_schema_array_items():
    schema = {
        "type": "array",
    }
    cleaned = sanitize_schema(schema)
    assert cleaned["type"] == "ARRAY"
    assert "items" in cleaned
    assert cleaned["items"]["type"] == "STRING"


def test_sanitize_schema_prune_required():
    schema = {
        "type": "object",
        "properties": {
            "foo": {"type": "string"},
        },
        "required": ["foo", "non_existent_prop"],
    }
    cleaned = sanitize_schema(schema)
    assert cleaned["required"] == ["foo"]


def test_sanitize_schema_const_to_enum():
    schema = {
        "type": "string",
        "const": "exact_value",
    }
    cleaned = sanitize_schema(schema)
    assert "const" not in cleaned
    assert cleaned["enum"] == ["exact_value"]
