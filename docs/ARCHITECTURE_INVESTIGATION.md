# Antigravity IDE Application Architecture & Observability Investigation

## 1. Executive Summary & Objective

The objective of this investigation is to understand the runtime architecture, internal communication patterns, data storage structures, and diagnostic interfaces of Google Antigravity IDE (Electron version 39.2.3, application version 1.107.0, extension `google.antigravity` version 0.2.0).

Using the evidence-driven methodology outlined in the REA reference project (Reverse Engineer Anything), we have analyzed the running processes, network sockets, local filesystems, log streams, SQLite databases, and binary wire protocols to establish a 100% verified factual foundation for the **Antigravity Observer** platform.

No modifications were made to the original Antigravity installation. All diagnostic and instrumentation methods rely on supported read-only interfaces, live process inspections, local log tailing, read-only SQLite queries, and internal HTTPS RPC queries.

---

## 2. Process & Component Architecture

### 2.1 Process Hierarchy
Through process tree analysis (`ps aux`, `lsof`, `pgrep`), Antigravity consists of the following components:

```
[Antigravity IDE (Electron Main Process)]
  ├── [GPU Process Helper] (--type=gpu-process)
  ├── [Crashpad Handler] (chrome_crashpad_handler)
  ├── [Renderer Windows] (Antigravity IDE Helper (Renderer) --type=renderer)
  │     ├── Workspace Window (window1, window2)
  │     └── Cascade Chat Webview (vscode-webview://...)
  ├── [Extension Host] (Antigravity IDE Helper (Plugin) --type=utility)
  │     ├── Extension: google.antigravity (v0.2.0)
  │     ├── Extension: henrikdev.ag-quota (v1.2.0)
  │     └── Standard VS Code extensions
  └── [Language Server Binary] (language_server_macos_arm)
        ├── Listen Ports: 51676 (HTTPS Connect RPC), 51677 (LSP), 51687 (Internal)
        ├── Outbound Connections: daily-cloudcode-pa.googleapis.com:443 (TLS)
        └── SQLite Stores: ~/.gemini/antigravity-ide/conversations/*.db
```

### 2.2 The Language Server (`language_server_macos_arm`)
- **Binary Path**: `/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin/language_server_macos_arm`
- **Binary Architecture**: Mach-O 64-bit arm64 executable, compiled Go binary (~131 MB).
- **Execution Arguments (verified live)**:
  - `--enable_lsp`
  - `--csrf_token <UUID>`: Secret CSRF token used for authenticating local RPC calls.
  - `--extension_server_port <PORT>`: Callback port hosted by the VS Code extension host.
  - `--extension_server_csrf_token <UUID>`: Secret token protecting extension callbacks.
  - `--workspace_id <ID>`: E.g. `file_Users_sachin_projects_antiglaude_bridge`.
  - `--cloud_code_endpoint https://daily-cloudcode-pa.googleapis.com`: Cloud backend endpoint.
  - `--subclient_type ide`
  - `--app_data_dir antigravity-ide`

### 2.3 Network Sockets & Protocols
- **Port 51676 (HTTPS Connect Protocol)**:
  - Uses self-signed TLS (`https://127.0.0.1:<port>`).
  - Implements the Connect protocol (`Connect-Protocol-Version: 1`).
  - Authenticated via header: `X-Codeium-Csrf-Token: <csrf_token>`.
  - Services: `/exa.language_server_pb.LanguageServerService/*`
    - `GetUserStatus`: Returns user identity, email (`khodwesarvesh007@gmail.com`), plan (`TEAMS_TIER_PRO`), available model configurations (`cascadeModelConfigData.clientModelConfigs`), remaining quota fractions, and reset timestamps.
    - `RetrieveUserQuotaSummary`: Returns quota groups (`Gemini Models`, `Claude Models`) with 5-hour and weekly bucket limits (`gemini-weekly`, `gemini-5h`), remaining fractions, and exact ISO reset times.
    - `GetUnleashData`: Feature flag evaluation and account health check.
- **Port 51677 (LSP Protocol)**:
  - Standard Language Server Protocol JSON-RPC for code diagnostics, completions, and edits.
- **External Outbound (daily-cloudcode-pa.googleapis.com:443)**:
  - Outbound TLS 1.3 connections handling `v1internal:streamGenerateContent?alt=sse`, `loadCodeAssist`, and `fetchAvailableModels`.

---

## 3. Data Storage & Log Structures

### 3.1 IDE Session Logs
Located in `~/Library/Application Support/Antigravity IDE/logs/<session_timestamp>/`:

1. **`ls-main.log`**:
   - Contains stderr and stdout from `language_server_macos_arm`.
   - Records every LLM interaction with microsecond precision:
     ```
     2026-11-04 00:54:39.319 [error] [LS Main stderr] ERROR: logging before google.Init: I1104 00:54:39.318895  482872 http_helpers.go:228] URL: https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse Trace: 0x5bbf7d826e5b992d ResponseID: 7zTqasH3M7f34-EP8czUyQk
     ```
   - Observable attributes:
     - Timestamp (`2026-11-04 00:54:39.319`)
     - Thread/Goroutine ID (`482872`)
     - Source file & line (`http_helpers.go:228`)
     - API URL (`https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse`)
     - Trace ID (`0x5bbf7d826e5b992d`)
     - Response ID (`7zTqasH3M7f34-EP8czUyQk`)

2. **`cloudcode.log`**:
   - Records high-level CloudCode extension requests:
     ```
     2026-11-04 00:45:32.715 [info] [CloudCode] POST v1internal:loadCodeAssist traceId: 77a9900b8647f888
     2026-11-04 00:45:33.951 [info] [CloudCode] POST v1internal:fetchAvailableModels traceId: d81e4efac4963262
     ```

3. **`window*/exthost/output_logging_*/2-Antigravity Quota.log`**:
   - Records live periodic updates from the quota extension:
     - Available models: Gemini 3.8 Flash (High), Gemini 3.8 Flash (Medium), Gemini 3.8 Flash (Low), Claude Sonnet 4.6 (Thinking), Claude Opus 4.6 (Thinking), GPT-OSS 120B (Medium).
     - Quota snapshots: prompt credits (available: 500, monthly: 50,000, used_percentage: 99%).

### 3.2 Transcripts Directory (`~/.gemini/antigravity-ide/brain/<conversation-id>/`)
- **`transcript.jsonl`** & **`transcript_full.jsonl`**:
  - Located in: `~/.gemini/antigravity-ide/brain/<conversation-id>/.system_generated/logs/`
  - Each entry is a single JSON line:
    - `step_index`: Sequential integer index of the step (0, 1, 2, ...).
    - `source`: `USER_EXPLICIT` (user prompt), `MODEL` (agent output), `SYSTEM` (instructions, transcripts, knowledge).
    - `type`: Step type identifier:
      - `USER_INPUT`: User query
      - `PLANNER_RESPONSE`: LLM reasoning, thought process, and proposed tool calls
      - `RUN_COMMAND`: Shell command execution
      - `LIST_DIRECTORY`: Workspace directory listing
      - `VIEW_FILE`: File viewer
      - `GREP_SEARCH`: Code search
      - `SEARCH_WEB`: Web search
      - `READ_URL_CONTENT`: Fetch URL content
      - `BROWSER_SUBAGENT`: Browser subagent launch
      - `ASK_QUESTION`: User interactive modal
      - `CODE_ACTION`: File modification
    - `status`: Step outcome (`DONE`, `ERROR`, `RUNNING`).
    - `created_at`: UTC ISO timestamp (e.g., `2026-11-03T19:24:24Z`).
    - `thinking`: Model chain-of-thought text (reasoning trace).
    - `tool_calls`: Array of tool invocations with name and parameters.
    - `content`: Execution result content or user text.

### 3.3 SQLite Conversation Stores (`~/.gemini/antigravity-ide/conversations/<conversation-id>.db`)
Stores structured trajectory data in WAL mode (`.db-wal`):
- **`trajectory_meta`**:
  - `trajectory_id`: UUID of trajectory (e.g., `b4add242-a4b5-4719-990a-6a9749838bda`).
  - `cascade_id`: Conversation ID (e.g., `6ebace7f-40db-4152-96c2-18bf7ac33f4c`).
- **`steps`**:
  - `idx`: Step index.
  - `step_type`: Numerical type (`14` = user input, `15` = planner response, `21` = run command, etc.).
  - `status`: Numerical status (`3` = DONE).
  - `metadata`: Binary protobuf containing execution metadata, sessionID, and ResponseID.
  - `step_payload`: Binary protobuf containing tool arguments and result payloads.
- **`gen_metadata`**:
  - `idx`: Generation sequence index.
  - `size`: Byte length of generation metadata blob.
  - `data`: Complete generation snapshot protobuf.

---

## 4. Reverse Engineered Protobuf Wire Format (`gen_metadata`)

Through custom tag-length-value (TLV) wire format decoding of `gen_metadata.data`, we decoded the exact layout of Antigravity's generation metadata:

- **Root Message**:
  - `Field 1` (length-delimited): **`GenerationContext`** (complete context of the generation):
    - `Subfield 2` (repeated length-delimited): Conversation message history snapshots.
    - `Subfield 10` (repeated length-delimited): Step index references.
    - `Subfield 11` & `12` (length-delimited): Generation timestamps and durations.
    - `Subfield 15` (length-delimited): Generation parameters:
      - Max tokens: `65536`
      - Stop tokens: `<|user|>`, `<|bot|>`, `<|context_request|>`, `<|endoftext|>`, `<|end_of_turn|>`
    - `Subfield 16` (repeated length-delimited): System prompts & instruction sections (`identity`, `mcp_servers`, `web_application_development`, `customizations`, `skills`, `artifacts`, `guidelines`, etc.) with exact byte lengths.
    - `Subfield 17` (length-delimited): **`TokenUsageAndMetadata`**:
      - `Subfield 2` (length-delimited):
        - `Key 5` (varint): **`prompt_tokens`** (e.g. `123,862` tokens!)
        - `Key 2` (varint): **`output_tokens`** (e.g. `5,088` tokens)
        - `Key 10` (varint): **`thinking_tokens`** / reasoning tokens (e.g. `954` tokens)
        - `Key 11` (length-delimited string): **`response_id`** (e.g. `CjXqauGKBaSvz7sPsIfQ4Qk`)
        - `Key 8` (message): `sessionID` (`-3750763034362895579`)
      - `Subfield 4` (string): Request trace ID hash (`f95e41397b19b4de`).
    - `Subfield 19` (string): Backend model ID (`gemini-3.8-flash-n`).
    - `Subfield 20` (repeated key-value):
      - `model_enum`: `MODEL_PLACEHOLDER_M318`
      - `trajectory_id`: `b4add242-a4b5-4719-990a-6a9749838bda`
      - `used_claude`: `false`
      - `last_step_index`: Step index string
    - `Subfield 21` (string): **`model_display_name`** (`Gemini 3.8 Flash (High)`).

---

## 5. Event Correlation Graph

Every interaction in Antigravity can be correlated across four layers:

```
[1. ls-main.log]
    URL: .../v1internal:streamGenerateContent?alt=sse
    Trace: 0xc6ec949d3394c93b
    ResponseID: OjTqaqKXMMnn4-EP1azuiQo
    Timestamp: 2026-11-04 00:51:44.340
         │
         │ (Matched by ResponseID / TraceID / Timestamp)
         ▼
[2. SQLite gen_metadata & steps]
    idx: 52 (Step 154)
    ResponseID: OjTqaqKXMMnn4-EP1azuiQo
    Model: Gemini 3.8 Flash (High) (backend: gemini-3.8-flash-n)
    Prompt Tokens: 86,412
    Output Tokens: 2,890
    Thinking Tokens: 165
         │
         │ (Matched by Step Index)
         ▼
[3. transcript.jsonl (Step Index 154)]
    type: PLANNER_RESPONSE
    thinking: "Initial focus is on defining the scope..."
    tool_calls: [run_command: { CommandLine: "tail -n 30 ..." }]
    created_at: 2026-11-03T19:21:44Z
         │
         │ (Next Step Index 155)
         ▼
[4. transcript.jsonl (Step Index 155)]
    type: RUN_COMMAND
    status: DONE
    exit_code: 0
    content: "Command stdout / output..."
```

This correlation guarantees:
1. Complete visibility into prompt & output tokens for every turn.
2. Direct correlation between LLM reasoning, tool proposals, and tool execution outcomes.
3. Microsecond-accurate latency metrics.
4. Historical replay and multi-step agent timeline visualization.

---

## 6. Distinguishing Verified Facts from Assumptions

| Dimension | Verified Fact (with Evidence) | Assumption / Non-Observable |
|:---|:---|:---|
| **API Endpoints** | Verified via `ls-main.log` and binary strings (`https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse`). | We do not assume Google's internal upstream server topology. |
| **Model Names** | Verified via `gen_metadata` (subfield 21: `Gemini 3.8 Flash (High)`, subfield 19: `gemini-3.8-flash-n`) and `2-Antigravity Quota.log`. | None; model identity is directly observable. |
| **Token Counts** | Verified via `gen_metadata` (subfield 17: prompt tokens, output tokens, thinking tokens). | We do not estimate tokens using string heuristics when real counts exist. |
| **Quota & Limits** | Verified live via Language Server HTTPS Connect RPC (`/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary`). | Quota numbers are queried directly from the running language server. |
| **SSE Stream Chunks** | Verified via `ls-main.log` (`?alt=sse`) and trajectory step incremental commits. | Raw TLS TCP packets between language server and Google Cloud are encrypted; we observe the streaming events at the application boundary (log + step arrival). |
