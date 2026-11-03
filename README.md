# Antiglaude Bridge & Developer Observability Platform

A production-grade local compatibility bridge and developer observability gateway connecting **Claude Code** (and Anthropic Messages API clients) with **Google Gemini / Antigravity Cloud Code inference models**, coupled with deep telemetry and real-time execution observability.

---

## Key Capabilities

1. **Claude Code Protocol Gateway (`gateway/`)**:
   - Exposes an Anthropic Messages API (`POST /v1/messages`, `GET /v1/models`, `POST /v1/messages/count_tokens`).
   - Translates Anthropic messages, thinking blocks, and tool calls (`Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`) to Google Gemini / Cloud Code formats.
   - Streaming SSE support with proper event ordering (`message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`, and keep-alive `ping` heartbeats).
   - Multi-provider support:
     - **Direct Gemini API** (`GEMINI_API_KEY`) for Gemini 2.5 Flash, Gemini 1.5 Pro, Gemini 2.0 Flash Thinking, etc.
     - **Antigravity / Cloud Code Backend** with automatic session token management, quota detection, and account rotation.
   - Built-in reliability: backoff jitter, circuit breakers, watchdog timers, and session state preservation.

2. **Antigravity Developer Observability (`antigravity_observer/`)**:
   - Live inspection of local Antigravity Language Server RPC (`GetUserStatus`, `RetrieveUserQuotaSummary`).
   - Protobuf wire-format telemetry decoder (`prompt_tokens`, `output_tokens`, `thinking_tokens`, exact model name).
   - Unified execution turns correlating logs, SQLite state, and interaction transcripts.
   - Live Web UI dashboard with real-time SSE stream.

---

## Architecture Overview

```
┌─────────────────────────────────┐
│        Claude Code CLI          │
│   (ANTHROPIC_BASE_URL=localhost)│
└────────────────┬────────────────┘
                 │ Anthropic Messages API (/v1/messages)
                 ▼
┌─────────────────────────────────┐
│         Gateway Bridge          │
│  - Protocol Translation Layer   │
│  - Tool Definition Sanitizer    │
│  - SSE Heartbeat & Watchdogs    │
│  - Multi-Provider Adapter       │
└───────┬─────────────────┬───────┘
        │                 │
        ▼                 ▼
┌───────────────┐ ┌─────────────────────────┐
│  Gemini API   │ │ Antigravity Cloud Code  │
│  (Direct key) │ │ (OAuth / Local state)   │
└───────────────┘ └─────────────────────────┘
```

---

## Quick Start

### 1. Requirements
- Python 3.10+
- Node.js 18+ (for Claude Code CLI)
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code` or `brew install claude-code`)

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/sksarvesh007/antiglaude-bridge.git
cd antiglaude-bridge

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Running the Gateway
```bash
# Using Gemini API key
export GEMINI_API_KEY="your-gemini-api-key"
python3 -m gateway.server --port 8080

# Or run with Antigravity Observer integration
python3 -m gateway.server --port 8080 --with-observer
```

### 4. Configuring Claude Code
Set Claude Code to use the local gateway:
```bash
export ANTHROPIC_BASE_URL="http://localhost:8080"
export ANTHROPIC_API_KEY="test"

# Run Claude Code CLI
claude
```

---

## Security & Privacy Notice
This project runs entirely locally on your machine.
- No telemetry or tokens are sent to external third parties other than the configured upstream inference provider.
- All secrets, tokens, credentials, and local databases are strictly excluded via `.gitignore`.
- Always keep your `.env` and `credentials.json` private.

---

## License
MIT
