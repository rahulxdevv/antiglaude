# Antiglaude Bridge ⚡

[![CI](https://github.com/sksarvesh007/antiglaude-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/sksarvesh007/antiglaude-bridge/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sksarvesh007/antiglaude-bridge?include_prereleases&color=blue)](https://github.com/sksarvesh007/antiglaude-bridge/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-6366f1.svg)](https://code.claude.com)
[![Google Antigravity](https://img.shields.io/badge/Google-Antigravity%20Ready-4285f4.svg)](https://antigravity.google)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A robust, production-quality local compatibility gateway and developer observability platform connecting **Claude Code CLI** (and any Anthropic Messages API client) with **Google Antigravity & Gemini inference models**.

---

## 📑 Table of Contents
- [Why Antiglaude Bridge?](#-why-antiglaude-bridge)
- [Feature Comparison](#-feature-comparison-vs-community-proxies)
- [Architecture](#-architecture)
- [Quick Start](#-installation--quick-start)
- [Using with Claude Code](#-using-with-claude-code)
- [Testing & Verification](#-testing--verification)
- [Observability Dashboard](#-antigravity-observer-integration)
- [Frequently Asked Questions (FAQ)](#-frequently-asked-questions-faq)
- [Security & Privacy](#-security--privacy)
- [License](#-license)

---

## 🚀 Why Antiglaude Bridge?

While initial community scripts paved the way, real-world agentic development exposed critical failure points:
- **Token Expiry 401s**: Hardcoded or extracted database tokens expire after 60 minutes, crashing active agent sessions.
- **Protobuf Schema 400s**: Claude Code sends advanced JSON Schema constructs (`propertyNames`, `anyOf`, `$schema`) that cause Google's protobuf parser to reject tool declarations.
- **Safety / Identity 429 Traps**: Untreated system prompt headers (like `x-anthropic-billing-header` or vendor self-identifications) trip upstream quota filters.
- **SSE Watchdog Drops**: Long multi-step reasoning turns cause Claude Code to time out if no keep-alive events are emitted.

**Antiglaude Bridge solves all of these by engineering a true protocol translation gateway:**
1. **Zero-Touch Auto-Refresh**: Extracts refresh tokens from local Antigravity state (`state.vscdb`) and transparently re-issues 1-hour access tokens before expiry.
2. **OpenAPI Protobuf Sanitizer**: Uses strict allowlisting and type normalizations (`STRING`, `OBJECT`, `ARRAY`) to guarantee 100% schema compatibility across all 28 Claude tools.
3. **Identity & Billing Scrubbers**: Neutralizes third-party identity lines and strips `x-anthropic-billing-header` triggers.
4. **Resilient SSE Streaming**: Emits accurate Anthropic event streams (`message_start`, `content_block_start/delta/stop`, `message_delta`, `message_stop`) with 15s keep-alive `ping` watchdogs.
5. **Integrated Observability**: Directly logs execution turns, latency, and token metrics into the built-in Antigravity Observer platform.

---

## 📊 Feature Comparison vs Community Proxies

| Feature | Antiglaude Bridge ⚡ | Basic Forwarding Proxies |
| :--- | :--- | :--- |
| **Authentication** | **Zero-Touch Auto-Refresh** via permanent refresh token | Static 60-minute token (fails on expiry) |
| **Tool Calling** | **100% Claude Code 2.1+ compatible** (sanitizes `propertyNames`) | ❌ Fails with `Unknown name "propertyNames"` (HTTP 400) |
| **Quota Protection** | **Auto-scrubs billing headers & vendor identity** | ❌ Fails with 429 `RESOURCE_EXHAUSTED` |
| **Streaming Reliability** | **15s Keep-Alive SSE Watchdog Pings** | Hangs on long reasoning/thinking steps |
| **CLI & Packaging** | Native Python CLI (`antiglaude status/start/claude`) | Node.js / npm script |
| **Observability** | Built-in SQLite trace logger + SSE web dashboard | Terminal console logs |

---

## 📐 Architecture

```
┌──────────────────────────────────────────────┐
│               Claude Code CLI                │
│    (ANTHROPIC_BASE_URL=http://localhost:8080)│
└──────────────────────┬───────────────────────┘
                       │ Anthropic Messages API (/v1/messages)
                       ▼
┌──────────────────────────────────────────────┐
│           Antiglaude Bridge Gateway          │
│  ┌────────────────────────────────────────┐  │
│  │ Protocol Translation & Identity Scrub  │  │
│  ├────────────────────────────────────────┤  │
│  │ Tool Schema Protobuf Sanitizer         │  │
│  ├────────────────────────────────────────┤  │
│  │ Auto-Refreshing Token Manager (ya29)   │  │
│  ├────────────────────────────────────────┤  │
│  │ SSE Stream Parser & Keep-Alive Watchdog│  │
│  └────────────────────────────────────────┘  │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│   Google Cloud Code / Gemini Inference API   │
│   - Claude Sonnet 4.6 (Thinking)             │
│   - Claude Opus 4.6 (Thinking)               │
│   - Gemini 3 Flash / 2.5 Pro                 │
└──────────────────────────────────────────────┘
```

---

## 🛠️ Installation & Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- Claude Code CLI installed:
  ```bash
  # Via Homebrew (macOS)
  brew install claude-code

  # Or via npm
  npm install -g @anthropic-ai/claude-code
  ```
- Google Antigravity installed and logged in (or Google Cloud Code credentials).

### 2. Clone & Setup
```bash
git clone https://github.com/sksarvesh007/antiglaude-bridge.git
cd antiglaude-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Verify Health & Account Status
Run the built-in diagnostic CLI:
```bash
antiglaude status
# or: python3 -m gateway.cli status
```
Output:
```text
Checking Antiglaude Bridge status...
Found 2 local Antigravity state database(s):
  - /Users/.../Library/Application Support/Antigravity/User/globalStorage/state.vscdb
OAuth Token: Active (len=261)
Project ID: aicode-consumers
Account Tier: g1-pro-tier
```

### 4. Launch the Bridge
```bash
# Using the launcher script
./run_bridge.sh 8080

# Or via the CLI command
antiglaude start --port 8080
```

---

## 💻 Using with Claude Code

### One-Command Quick Launch
Run Claude Code directly through the bridge without changing your global environment:
```bash
antiglaude claude "Inspect this repository and fix any issues"
```

### System Configuration Setup
To configure Claude Code permanently:

1. Create or edit `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080",
    "ANTHROPIC_API_KEY": "test-bridge-token",
    "ANTHROPIC_MODEL": "claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gemini-3-flash",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-6-thinking"
  }
}
```

2. Ensure `hasCompletedOnboarding` is set in `~/.claude.json`:
```json
{
  "hasCompletedOnboarding": true
}
```

3. Export environment variables in your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
export ANTHROPIC_API_KEY="test"
```

4. Launch Claude Code:
```bash
claude
```

---

## 🧪 Testing & Verification

Antiglaude Bridge includes a complete automated test suite covering protocol translation, schema sanitization, streaming SSE, and live end-to-end inference:

```bash
# Run all unit and protocol tests
pytest tests/ -v
```

Test coverage includes:
- `tests/test_schema_sanitizer.py`: Tests `propertyNames` removal, `const` to `enum` conversions, `anyOf`/`allOf` flattening, and protobuf type normalization.
- `tests/test_request_converter.py`: Tests identity scrubbers, billing header stripping, and model alias mappings.
- `tests/test_response_converter.py`: Tests Google SSE chunk parsing, thinking deltas, tool call events, and token usage metadata.
- `tests/test_server_endpoints.py`: Tests `/health`, `/v1/models`, and `/v1/messages/count_tokens`.
- `tests/test_live_inference.py`: Live integration tests against the active upstream models verifying streaming, non-streaming, and function calling.

---

## 🔍 Antigravity Observer Integration

Antiglaude Bridge integrates seamlessly with the companion **Antigravity Observer Platform**:
- Live request telemetry and token analytics logged automatically to SQLite.
- Real-time SSE dashboard at `http://localhost:8000`.
- Native inspection of Language Server RPC, SQLite states, and protobuf metadata.

To launch the observer alongside the gateway:
```bash
antigravity-observer serve --port 8000
```

---

## ❓ Frequently Asked Questions (FAQ)

### How is Antiglaude Bridge different from standard forwarding proxies?
Standard forwarding proxies directly read an expiring `apiKey` from SQLite that becomes invalid after 60 minutes, and fail with `Unknown name "propertyNames"` when Claude Code 2.1+ executes tools. Antiglaude Bridge discovers the underlying refresh token, automatically re-authenticates with Google's token servers, sanitizes all JSON schemas into compliant Protobuf types, and scrubs billing headers that trigger 429 quota exhaustion.

### Does this require modifying Google Antigravity?
**No.** Antiglaude Bridge is completely non-invasive. It reads only local configuration databases on your local disk in read-only mode, without patching any files in Antigravity or VS Code.

### Which models are supported?
- `claude-sonnet-4-6` / `claude-3-7-sonnet-latest`
- `claude-opus-4-6-thinking` / `claude-3-opus-latest`
- `gemini-3-flash` / `claude-3-5-haiku-latest`
- `gemini-2.5-pro`

### Does it work with Claude Code's agentic tools?
**Yes.** All 28 Claude Code tools (`Bash`, `Edit`, `Read`, `Write`, `Glob`, `Grep`, etc.) are fully supported and verified through the schema sanitizer.

---

## 🔒 Security & Privacy

- **Zero Secret Exposure**: The gateway runs 100% locally on your machine (`127.0.0.1`).
- **Strict `.gitignore`**: All credentials, tokens, databases, logs, and sensitive paths are permanently excluded from version control.
- **No Third-Party Telemetry**: Requests flow strictly between your local client and the configured Google Cloud endpoint.

---

## 🏷️ Keywords & Search Topics
`claude-code`, `antigravity`, `google-antigravity`, `gemini`, `claude-proxy`, `anthropic`, `anthropic-api`, `claude-code-router`, `llm-gateway`, `ai-agent`, `claude-sonnet`, `gemini-api`, `code-assistant`, `developer-tools`, `observability`

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
