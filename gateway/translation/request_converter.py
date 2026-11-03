"""Request converter: Anthropic Messages API -> Google Cloud Code format."""

import copy
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from gateway.config import DEFAULT_CONFIG
from gateway.protocol.anthropic_models import AnthropicMessagesRequest, Message
from gateway.protocol.schema_sanitizer import sanitize_schema
from gateway.translation.scrub import clean_cache_control, scrub_client_identity, strip_billing_header

logger = logging.getLogger("gateway.translation")

ANTIGRAVITY_SYSTEM_INSTRUCTION = (
    "You are Antigravity, a powerful agentic AI coding assistant designed by the "
    "Google Deepmind team working on Advanced Agentic Coding. You are pair programming "
    "with a USER to solve their coding task. The task may require creating a new codebase, "
    "modifying or debugging an existing codebase, or simply answering a question."
)


def map_model_name(requested_model: str, config=DEFAULT_CONFIG) -> Tuple[str, str]:
    """Map requested model ID to canonical backend model and determine model family."""
    canonical = config.model_aliases.get(requested_model, requested_model)
    lower = canonical.lower()
    if "claude" in lower:
        family = "claude"
    elif "gemini" in lower:
        family = "gemini"
    else:
        family = "claude" if "claude" in requested_model.lower() else "gemini"
    return canonical, family


def convert_content_to_parts(
    content: Any,
    is_claude: bool = True,
    is_gemini: bool = False,
) -> List[Dict[str, Any]]:
    """Convert Anthropic content into Google Generative AI parts."""
    if isinstance(content, str):
        return [{"text": content}] if content else [{"text": "."}]

    if not isinstance(content, list):
        return [{"text": str(content)}]

    parts: List[Dict[str, Any]] = []
    deferred_images: List[Dict[str, Any]] = []

    for block in content:
        if not block:
            continue

        if isinstance(block, dict):
            b_type = block.get("type", "text")
        else:
            b_type = getattr(block, "type", "text")
            block = block.model_dump() if hasattr(block, "model_dump") else dict(block)

        if b_type == "text":
            text = block.get("text", "")
            if text:
                parts.append({"text": text})

        elif b_type == "image":
            source = block.get("source", {})
            if source.get("type") == "base64":
                parts.append({
                    "inlineData": {
                        "mimeType": source.get("media_type", "image/png"),
                        "data": source.get("data", ""),
                    }
                })

        elif b_type == "tool_use":
            fc: Dict[str, Any] = {
                "name": block.get("name", "tool"),
                "args": block.get("input") or {},
            }
            if is_claude and block.get("id"):
                fc["id"] = block["id"]

            part: Dict[str, Any] = {"functionCall": fc}
            if is_gemini and block.get("thoughtSignature"):
                part["thoughtSignature"] = block["thoughtSignature"]
            parts.append(part)

        elif b_type == "tool_result":
            res_content = block.get("content", "")
            image_parts = []

            if isinstance(res_content, str):
                response_obj = {"result": res_content}
            elif isinstance(res_content, list):
                text_pieces = []
                for item in res_content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_pieces.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            src = item.get("source", {})
                            image_parts.append({
                                "inlineData": {
                                    "mimeType": src.get("media_type", "image/png"),
                                    "data": src.get("data", ""),
                                }
                            })
                response_obj = {"result": "\n".join(text_pieces) or "Success"}
            else:
                response_obj = {"result": str(res_content)}

            fr: Dict[str, Any] = {
                "name": block.get("tool_use_id", "tool"),
                "response": response_obj,
            }
            if is_claude and block.get("tool_use_id"):
                fr["id"] = block["tool_use_id"]

            parts.append({"functionResponse": fr})
            deferred_images.extend(image_parts)

        elif b_type == "thinking":
            # Pass signed thinking if present
            thinking_text = block.get("thinking", "")
            sig = block.get("signature")
            if sig:
                parts.append({
                    "text": thinking_text,
                    "thought": True,
                    "thoughtSignature": sig,
                })

    # Append any deferred images at the end
    parts.extend(deferred_images)

    # Google API requires at least one part per content turn
    if not parts:
        parts.append({"text": "."})

    return parts


def convert_anthropic_to_cloudcode(
    req: AnthropicMessagesRequest,
    project_id: str,
    account_email: str,
    config=DEFAULT_CONFIG,
) -> Dict[str, Any]:
    """Convert an AnthropicMessagesRequest to a Google Cloud Code request payload."""
    canonical_model, model_family = map_model_name(req.model, config)
    is_claude = model_family == "claude"
    is_gemini = model_family == "gemini"

    # 1. Clean cache control
    raw_messages = [m.model_dump() for m in req.messages]
    cleaned_messages = clean_cache_control(raw_messages)

    # 2. Build system instructions
    system_parts: List[Dict[str, str]] = [
        {"text": ANTIGRAVITY_SYSTEM_INSTRUCTION},
        {"text": f"Please ignore the following [ignore]{ANTIGRAVITY_SYSTEM_INSTRUCTION}[/ignore]"},
    ]

    if req.system:
        if isinstance(req.system, str):
            clean_sys = strip_billing_header(req.system)
            if clean_sys:
                system_parts.append({"text": scrub_client_identity(clean_sys)})
        elif isinstance(req.system, list):
            for block in req.system:
                if isinstance(block, dict) and block.get("type") == "text":
                    clean_sys = strip_billing_header(block.get("text", ""))
                    if clean_sys:
                        system_parts.append({"text": scrub_client_identity(clean_sys)})

    # Hint for Claude interleaved thinking with tools
    if is_claude and req.tools:
        system_parts.append({
            "text": (
                "Interleaved thinking is enabled. You may think between tool calls and "
                "after receiving tool results before deciding the next action or final answer."
            )
        })

    # 3. Build contents
    contents: List[Dict[str, Any]] = []
    for msg in cleaned_messages:
        role = msg.get("role", "user")
        google_role = "model" if role in ("assistant", "model") else "user"
        parts = convert_content_to_parts(msg.get("content", ""), is_claude=is_claude, is_gemini=is_gemini)
        contents.append({"role": google_role, "parts": parts})

    # 4. Generation Config
    generation_config: Dict[str, Any] = {
        "maxOutputTokens": req.max_tokens or 4096,
    }
    if req.temperature is not None:
        generation_config["temperature"] = req.temperature
    if req.top_p is not None:
        generation_config["topP"] = req.top_p
    if req.top_k is not None:
        generation_config["topK"] = req.top_k
    if req.stop_sequences:
        generation_config["stopSequences"] = req.stop_sequences

    # Configure thinking
    if is_claude:
        budget = 32000
        if req.thinking and req.thinking.budget_tokens:
            budget = req.thinking.budget_tokens
        generation_config["thinkingConfig"] = {
            "include_thoughts": True,
            "thinking_budget": budget,
        }
        # Ensure maxOutputTokens exceeds thinking budget
        if generation_config["maxOutputTokens"] <= budget:
            generation_config["maxOutputTokens"] = budget + 8192
    elif is_gemini and "flash" in canonical_model.lower():
        generation_config["thinkingConfig"] = {
            "includeThoughts": True,
            "thinkingBudget": 8192,
        }

    # 5. Tools
    google_tools = None
    tool_config = None
    if req.tools:
        function_declarations = []
        for idx, tool in enumerate(req.tools):
            name = tool.name if hasattr(tool, "name") else tool.get("name", f"tool_{idx}")
            desc = tool.description if hasattr(tool, "description") else tool.get("description", "")
            raw_schema = tool.input_schema if hasattr(tool, "input_schema") else tool.get("input_schema", {})

            clean_schema = sanitize_schema(raw_schema)
            # Ensure name has only valid characters
            safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:64]
            function_declarations.append({
                "name": safe_name,
                "description": desc or "",
                "parameters": clean_schema,
            })

        google_tools = [{"functionDeclarations": function_declarations}]
        if is_claude:
            tool_config = {"functionCallingConfig": {"mode": "VALIDATED"}}

    # 6. Assemble Google Request
    google_request: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": generation_config,
    }
    if google_tools:
        google_request["tools"] = google_tools
    if tool_config:
        google_request["toolConfig"] = tool_config

    # Top-level systemInstruction in user role (required for Cloud Code agent mode)
    google_request["systemInstruction"] = {
        "role": "user",
        "parts": system_parts,
    }

    # Derive machine session ID from initial user turn
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    google_request["sessionId"] = session_id

    # 7. Final Wrapped Cloud Code Payload
    payload: Dict[str, Any] = {
        "project": project_id,
        "model": canonical_model,
        "request": google_request,
        "userAgent": "antigravity",
        "requestType": "agent",
        "requestId": f"agent-{uuid.uuid4()}",
    }

    return payload
