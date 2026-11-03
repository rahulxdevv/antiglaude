#!/usr/bin/env bash
# Antiglaude Bridge Gateway Launcher (Dual Anthropic & OpenAI Compatible)
set -e

PORT=${1:-8080}
HOST=${2:-127.0.0.1}

echo "=========================================="
echo " Starting Antiglaude Bridge on http://${HOST}:${PORT}"
echo " Serving Anthropic & OpenAI API endpoints"
echo "=========================================="

if command -v uv >/dev/null 2>&1; then
    uv run python -m gateway.cli serve --host "$HOST" --port "$PORT"
else
    python3 -m gateway.cli serve --host "$HOST" --port "$PORT"
fi
