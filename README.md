# Antiglaude Bridge ⚡

[![CI](https://github.com/sksarvesh007/antiglaude-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/sksarvesh007/antiglaude-bridge/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/sksarvesh007/antiglaude-bridge?include_prereleases&color=blue)](https://github.com/sksarvesh007/antiglaude-bridge/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/package%20manager-uv-de5fe9.svg)](https://github.com/astral-sh/uv)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-6366f1.svg)](https://code.claude.com)
[![OpenAI Compatible](https://img.shields.io/badge/OpenAI%20API-Compatible-412991.svg)](https://platform.openai.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A high-performance local AI gateway and **OpenRouter-style LLM inference server** that connects **Claude Code CLI** and any **OpenAI-compatible application** to upstream **Google Cloud Code & Gemini models** (`claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gemini-3-flash`, `gemini-2.5-pro`).

---

## 📑 Table of Contents
- [⚡ Quick Start in 1 Command](#-quick-start-in-1-command)
- [✨ Core Capabilities](#-core-capabilities)
- [🌐 OpenRouter-Style OpenAI Endpoint (Build AI Apps)](#-openrouter-style-openai-endpoint-build-ai-apps)
  - [Python OpenAI SDK](#1-python-openai-sdk)
  - [Streaming Example](#2-streaming-example)
  - [cURL Request](#3-curl-request)
  - [Supported Model Codenames](#4-supported-model-codenames)
  - [Compatible Frameworks (LangChain, LlamaIndex, Cursor, Continue)](#5-compatible-frameworks)
- [💻 Claude Code Integration](#-claude-code-integration)
  - [One-Command Launch](#1-one-command-launch)
  - [Shell Environment Setup](#2-shell-environment-setup)
  - [Claude Code Auto Mode & Classifier Billing](#3-claude-code-auto-mode--classifier-billing)
- [🛠️ Installation with `uv`](#️-installation-with-uv)
- [📋 Makefile Command Reference](#-makefile-command-reference)
- [📐 Architecture](#-architecture)
- [🧪 Testing & Verification](#-testing--verification)
- [❓ Frequently Asked Questions (FAQ)](#-frequently-asked-questions-faq)
- [🔒 Security & Privacy](#-security--privacy)
- [📄 License](#-license)

---

## ⚡ Quick Start in 1 Command

No manual dependency setup required. With `make`, the environment is automatically prepared using [`uv`](https://github.com/astral-sh/uv) and started immediately:

```bash
# Clone the repository
git clone https://github.com/sksarvesh007/antiglaude-bridge.git
cd antiglaude-bridge

# 1-command launch: installs uv, sets up venv, installs dependencies, and starts the gateway
make start
# or: make serve
```

The gateway server starts at **`http://127.0.0.1:8080`**, ready to accept both **Anthropic** and **OpenAI** requests.

To immediately launch an interactive **Claude Code CLI** session wired to the bridge:
```bash
make claude
```

---

## ✨ Core Capabilities

- 🔄 **Dual Protocol Engine**:
  - **Anthropic Messages API** (`/v1/messages`): Full streaming SSE & tool use for Claude Code CLI.
  - **OpenAI Chat Completions API** (`/v1/chat/completions`): Drop-in OpenRouter-style inference for external AI apps, Python/TypeScript SDKs, LangChain, LlamaIndex, Cursor, and Continue.dev.
- 🔑 **Zero-Touch Auto-Refresh Authentication**: Discovers local Antigravity/Cloud Code refresh credentials (`state.vscdb`) and automatically re-authenticates 1-hour OAuth access tokens before expiration.
- 🛡️ **OpenAPI Protobuf Sanitizer**: Normalizes advanced JSON Schemas sent by Claude Code (`propertyNames`, `anyOf`, `const`) into Google-compatible Protobuf structures, preventing HTTP 400 schema errors.
- ⏱️ **SSE Keep-Alive Watchdog**: Emits 15-second heartbeat pings to prevent client timeouts during multi-step reasoning turns.
- 🎯 **Claude Code Auto-Mode Classifier Billing**: Implements the official protocol for `safeguards` and generates `safeguard_results`, preventing unnecessary billing prompts.
- ⚡ **Blazing Fast `uv` Tooling**: Built from the ground up for Astral's `uv` for instantaneous environment setups and deterministic packaging.

---

## 🌐 OpenRouter-Style OpenAI Endpoint (Build AI Apps)

Antiglaude Bridge acts as your own private local **OpenRouter**. Any tool or library that speaks the standard OpenAI API can point to `http://127.0.0.1:8080/v1` to execute inference across Google and Claude models without cloud API costs or rate-limit friction.

### 1. Python OpenAI SDK

```python
from openai import OpenAI

# Point to your local Antiglaude Bridge server
client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="sk-antiglaude"  # Any string accepted
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "You are a concise engineering assistant."},
        {"role": "user", "content": "What is the difference between a process and a thread?"}
    ]
)

print(response.choices[0].message.content)
```

### 2. Streaming Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="sk-antiglaude"
)

stream = client.chat.completions.create(
    model="claude-opus-4-6-thinking",
    messages=[{"role": "user", "content": "Write a quick Python script to download an image."}],
    stream=True
)

for chunk in stream:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)
```

### 3. cURL Request

```bash
# Non-streaming
curl -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Explain Rust ownership in 1 line."}]
  }'

# Streaming
curl -N -X POST http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test" \
  -d '{
    "model": "gemini-3-flash",
    "messages": [{"role": "user", "content": "Count from 1 to 5."}],
    "stream": true
  }'
```

### 4. Supported Model Codenames

You can request any of the following models (or standard aliases):

| Model Codename | Description | Upstream Target |
| :--- | :--- | :--- |
| `claude-sonnet-4-6` *(default)* | Fast, highly capable agentic reasoning | Claude 3.7 Sonnet |
| `claude-opus-4-6-thinking` | Deep multi-step reasoning with extended thought chains | Claude 3 Opus / Thinking |
| `gemini-3-flash` | Ultra-low latency, high-throughput completions | Gemini 3 Flash |
| `gemini-2.5-pro` | Comprehensive analytical and large-context model | Gemini 2.5 Pro |
| `claude-3-7-sonnet-latest` | Anthropic alias automatically routed | `claude-sonnet-4-6` |
| `claude-3-5-haiku-latest` | Fast Anthropic alias automatically routed | `gemini-3-flash` |

*Note: Antiglaude Bridge includes an intelligent heuristic fallback mapper. Even if an AI app requests arbitrary codenames (like `claude-fable-5-1` or `gpt-4o`), the bridge automatically normalizes the request to the highest-performing active Google model.*

### 5. Compatible Frameworks

Easily configure popular developer tools to use Antiglaude Bridge:

- **LangChain / LlamaIndex**: Set `openai_api_base="http://127.0.0.1:8080/v1"` and `openai_api_key="test"`.
- **Cursor / Continue.dev**: Configure custom OpenAI provider with URL `http://127.0.0.1:8080/v1`.
- **AutoGen / CrewAI**: Set `base_url="http://127.0.0.1:8080/v1"`.

---

## 💻 Claude Code Integration

### 1. One-Command Launch

Launch Claude Code with environment variables pre-configured in a single command:

```bash
# Interactive Claude Code session
make claude

# Run a headless task directly
make claude ARGS="-p 'Review the latest commit and run tests'"
```

### 2. Shell Environment Setup

To use Claude Code normally in any terminal window, add the following to your `~/.zshrc` or `~/.bashrc`:

```bash
# Claude Code -> Antiglaude Bridge
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080"
export ANTHROPIC_API_KEY="test"

# Optional: Disable external auto-mode classifier requests
export CLAUDE_CODE_AUTO_MODE_SERVER="0"
```

Then simply start the bridge and run Claude:
```bash
make serve &
claude
```

### 3. Claude Code Auto Mode & Classifier Billing

In Claude Code, "Auto Mode" runs background classifier checks. When using local gateways, Claude Code displays a warning if the gateway does not implement the auto-mode classifier protocol:

```text
We're changing auto mode to no longer charge for classifier requests in Claude Code.
However, this session isn't eligible because your requests go through 127.0.0.1:8080...
```

**Antiglaude Bridge fully resolves this:**
1. **Safeguard Protocol Handling**: The bridge recognizes the `safeguards` request parameter and returns structured `safeguard_results` (`dangerous_tool_use`, status `available`, outcome `not_flagged`) on every tool execution turn.
2. **Offline Classifier Bypass**: Setting `export CLAUDE_CODE_AUTO_MODE_SERVER="0"` instructs Claude Code to handle classifications locally without querying external billing classifiers.

---

## 🛠️ Installation with `uv`

If you prefer to manage the environment manually using `uv`:

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone the repository
git clone https://github.com/sksarvesh007/antiglaude-bridge.git
cd antiglaude-bridge

# 3. Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e .

# 4. Check token & account health
antiglaude status

# 5. Start the server
antiglaude serve --port 8080
```

---

## 📋 Makefile Command Reference

| Target | Description | Example |
| :--- | :--- | :--- |
| `make start` | Automatically configures dependencies with `uv` and runs the gateway | `make start` |
| `make serve` | Alias for `make start` (serves on port 8080) | `make serve PORT=8080` |
| `make claude` | Starts interactive Claude Code CLI connected to the bridge | `make claude` |
| `make status` | Inspects local Antigravity state, token health, and project tier | `make status` |
| `make test` | Installs test harness and executes test suite | `make test` |
| `make stop` | Finds and terminates any process listening on the configured port | `make stop PORT=8080` |
| `make clean` | Cleans `.venv`, pycache, build artifacts, and test caches | `make clean` |

---

## 📐 Architecture

```
┌─────────────────────────────┐         ┌─────────────────────────────┐
│       Claude Code CLI       │         │    External AI / OpenAI     │
│   (Anthropic Protocol)      │         │     (LangChain, SDKs)       │
└──────────────┬──────────────┘         └──────────────┬──────────────┘
               │ POST /v1/messages                     │ POST /v1/chat/completions
               ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Antiglaude Bridge Gateway                      │
│                                                                     │
│  ┌─────────────────────────────┐     ┌───────────────────────────┐  │
│  │   Anthropic SSE Translator  │     │  OpenAI Compatibility     │  │
│  │   & Safeguard Generator     │     │  Request/Response Parser  │  │
│  └──────────────┬──────────────┘     └──────────────┬────────────┘  │
│                 └──────────────────┬────────────────┘               │
│                                    ▼                                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ OpenAPI Protobuf Schema Sanitizer (strips propertyNames, etc)│  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │ Auto-Refreshing Token Manager (permanent refresh via state.db) │  │
│  ├───────────────────────────────────────────────────────────────┤  │
│  │ Keep-Alive Watchdog Engine (15s heartbeat pings)              │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │ Google Cloud Code REST / Protobuf
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│               Google Antigravity & Gemini Inference API             │
│   • Claude Sonnet 4.6 (Thinking)      • Gemini 3 Flash              │
│   • Claude Opus 4.6 (Thinking)        • Gemini 2.5 Pro              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🧪 Testing & Verification

Antiglaude Bridge includes an automated test suite verifying protocol translation, schema sanitization, OpenAI endpoint compatibility, and streaming events:

```bash
# Run tests with make (auto-installs test packages with uv)
make test
```

Verified test suites:
- `tests/test_openai_endpoint.py`: Validates `/v1/chat/completions` non-streaming and streaming chunk generation.
- `tests/test_schema_sanitizer.py`: Tests `propertyNames` removal, `const` to `enum` conversions, `anyOf`/`allOf` flattening, and protobuf type normalization.
- `tests/test_request_converter.py`: Tests identity scrubbers, billing header stripping, and model alias mappings.
- `tests/test_response_converter.py`: Tests Google SSE chunk parsing, thinking deltas, tool call events, and token usage metadata.
- `tests/test_server_endpoints.py`: Tests `/health`, `/v1/models`, and token counters.

---

## ❓ Frequently Asked Questions (FAQ)

### Can I build custom web apps or agents with this?
**Yes.** Antiglaude Bridge exposes an OpenAI-compatible `/v1/chat/completions` endpoint. Any standard OpenAI client, agent framework, or backend can make streaming or non-streaming requests simply by setting `base_url="http://127.0.0.1:8080/v1"`.

### How does token authentication work?
Antiglaude Bridge locates the local state database created when you log into Google Antigravity or Google Cloud Code. It retrieves the OAuth refresh token and automatically requests fresh 1-hour access tokens from Google OAuth servers before expiry. You never need to copy-paste API keys or worry about 60-minute token expiration.

### Does this require modifying Google Antigravity?
**No.** Antiglaude Bridge is completely non-invasive. It reads local configuration databases in read-only mode, without patching any files in Antigravity or VS Code.

### Does it work with Claude Code's agentic tools?
**Yes.** All 28 Claude Code tools (`Bash`, `Edit`, `Read`, `Write`, `Glob`, `Grep`, etc.) are fully supported and verified through the schema sanitizer.

---

## 🔒 Security & Privacy

- **100% Local**: The gateway runs strictly on your machine (`127.0.0.1`).
- **No Secret Leakage**: Credentials, tokens, databases, logs, and sensitive paths are permanently excluded from version control via `.gitignore`.
- **Zero Third-Party Telemetry**: Requests flow directly between your local client and the official Google endpoints.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
