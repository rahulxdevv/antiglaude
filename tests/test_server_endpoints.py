"""Tests for FastAPI server endpoints."""

import pytest
from fastapi.testclient import TestClient
from gateway.server import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_models_endpoint():
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0
    model_ids = [m["id"] for m in data["data"]]
    assert "claude-sonnet-4-6" in model_ids


def test_count_tokens_endpoint():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "Count these tokens please!"}
        ],
    }
    response = client.post("/v1/messages/count_tokens", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "input_tokens" in data
    assert data["input_tokens"] > 0
