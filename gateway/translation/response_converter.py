"""Streaming response converter: Google Cloud Code SSE -> Anthropic SSE."""

import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from gateway.protocol.sse_events import (
    content_block_delta_event,
    content_block_start_event,
    content_block_stop_event,
    message_delta_event,
    message_start_event,
    message_stop_event,
)

logger = logging.getLogger("gateway.response_converter")


class StreamParser:
    """Parses incoming Google SSE chunks into Anthropic SSE events."""

    def __init__(self, requested_model: str):
        self.requested_model = requested_model
        self.message_id = f"msg_{uuid.uuid4().hex}"
        self.has_emitted_start = False
        self.block_index = 0
        self.current_block_type: Optional[str] = None
        self.current_thinking_sig: Optional[str] = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.stop_reason: Optional[str] = None

        # For non-streaming accumulation
        self.accumulated_content: List[Dict[str, Any]] = []

    def parse_chunk(self, raw_line: str) -> List[str]:
        """Parse one SSE line and yield zero or more Anthropic SSE event strings."""
        if not raw_line.startswith("data:"):
            return []

        json_text = raw_line[5:].strip()
        if not json_text:
            return []

        events: List[str] = []
        try:
            data = json.loads(json_text)
            inner = data.get("response", data)

            # 1. Usage metadata
            usage = inner.get("usageMetadata", {})
            if usage:
                self.input_tokens = usage.get("promptTokenCount", self.input_tokens)
                self.output_tokens = usage.get("candidatesTokenCount", self.output_tokens)
                self.cache_read_tokens = usage.get("cachedContentTokenCount", self.cache_read_tokens)

            candidates = inner.get("candidates", [])
            first_cand = candidates[0] if candidates else {}
            content = first_cand.get("content", {})
            parts = content.get("parts", [])

            # 2. Emit message_start on first content part
            if not self.has_emitted_start and parts:
                self.has_emitted_start = True
                events.append(
                    message_start_event(
                        message_id=self.message_id,
                        model=self.requested_model,
                        input_tokens=self.input_tokens,
                        cache_read_tokens=self.cache_read_tokens,
                    )
                )

            # 3. Process parts
            for part in parts:
                if part.get("thought") is True:
                    text = part.get("text", "")
                    sig = part.get("thoughtSignature")
                    if sig:
                        self.current_thinking_sig = sig

                    if self.current_block_type != "thinking":
                        if self.current_block_type is not None:
                            events.append(content_block_stop_event(self.block_index))
                            self.block_index += 1

                        self.current_block_type = "thinking"
                        events.append(
                            content_block_start_event(
                                self.block_index,
                                {"type": "thinking", "thinking": ""},
                            )
                        )
                        self.accumulated_content.append({"type": "thinking", "thinking": text})
                    else:
                        if self.accumulated_content:
                            self.accumulated_content[-1]["thinking"] += text

                    events.append(
                        content_block_delta_event(
                            self.block_index,
                            {"type": "thinking_delta", "thinking": text},
                        )
                    )

                elif "text" in part:
                    text = part.get("text", "")
                    if text == "":
                        continue

                    # Transition from thinking or other block
                    if self.current_block_type != "text":
                        if self.current_block_type == "thinking" and self.current_thinking_sig:
                            events.append(
                                content_block_delta_event(
                                    self.block_index,
                                    {"type": "signature_delta", "signature": self.current_thinking_sig},
                                )
                            )
                            self.current_thinking_sig = None

                        if self.current_block_type is not None:
                            events.append(content_block_stop_event(self.block_index))
                            self.block_index += 1

                        self.current_block_type = "text"
                        events.append(
                            content_block_start_event(
                                self.block_index,
                                {"type": "text", "text": ""},
                            )
                        )
                        self.accumulated_content.append({"type": "text", "text": text})
                    else:
                        if self.accumulated_content:
                            self.accumulated_content[-1]["text"] += text

                    events.append(
                        content_block_delta_event(
                            self.block_index,
                            {"type": "text_delta", "text": text},
                        )
                    )

                elif "functionCall" in part:
                    fc = part["functionCall"]
                    fn_name = fc.get("name", "tool")
                    fn_args = fc.get("args") or {}
                    tool_id = fc.get("id") or f"toolu_{uuid.uuid4().hex[:20]}"
                    self.stop_reason = "tool_use"

                    if self.current_block_type == "thinking" and self.current_thinking_sig:
                        events.append(
                            content_block_delta_event(
                                self.block_index,
                                {"type": "signature_delta", "signature": self.current_thinking_sig},
                            )
                        )
                        self.current_thinking_sig = None

                    if self.current_block_type is not None:
                        events.append(content_block_stop_event(self.block_index))
                        self.block_index += 1

                    self.current_block_type = "tool_use"
                    tool_block = {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": fn_name,
                        "input": fn_args,
                    }
                    self.accumulated_content.append(tool_block)

                    events.append(
                        content_block_start_event(
                            self.block_index,
                            tool_block,
                        )
                    )
                    events.append(
                        content_block_delta_event(
                            self.block_index,
                            {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(fn_args),
                            },
                        )
                    )
                    events.append(content_block_stop_event(self.block_index))
                    self.block_index += 1
                    self.current_block_type = None

            # 4. Check finish reason
            finish_reason = first_cand.get("finishReason")
            if finish_reason and not self.stop_reason:
                if finish_reason == "MAX_TOKENS":
                    self.stop_reason = "max_tokens"
                elif finish_reason in ("STOP", "FINISH_REASON_UNSPECIFIED"):
                    self.stop_reason = "end_turn"

        except Exception as e:
            logger.debug("Error parsing SSE line: %s", e)

        return events

    def finalize(self) -> List[str]:
        """Close open blocks and emit final message_delta and message_stop."""
        events: List[str] = []

        # If start was never emitted (e.g. empty turn), emit it now
        if not self.has_emitted_start:
            self.has_emitted_start = True
            events.append(
                message_start_event(
                    message_id=self.message_id,
                    model=self.requested_model,
                    input_tokens=self.input_tokens,
                    cache_read_tokens=self.cache_read_tokens,
                )
            )

        # Close any open content block
        if self.current_block_type is not None:
            if self.current_block_type == "thinking" and self.current_thinking_sig:
                events.append(
                    content_block_delta_event(
                        self.block_index,
                        {"type": "signature_delta", "signature": self.current_thinking_sig},
                    )
                )
            events.append(content_block_stop_event(self.block_index))
            self.current_block_type = None

        # Emit message_delta
        events.append(
            message_delta_event(
                stop_reason=self.stop_reason or "end_turn",
                output_tokens=self.output_tokens,
                cache_read_tokens=self.cache_read_tokens,
            )
        )

        # Emit message_stop
        events.append(message_stop_event())
        return events
