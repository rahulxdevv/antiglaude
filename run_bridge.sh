#!/usr/bin/env bash
# Antiglaude Bridge Gateway Launcher
set -e

PORT=${1:-8080}
echo "=========================================="
echo " Starting Antiglaude Bridge on port $PORT"
echo "=========================================="

python3 -m gateway.cli start --port "$PORT"
