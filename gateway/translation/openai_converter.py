"""Translation layer: OpenAI Chat Completions <-> Anthropic Messages."""

import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from gateway.protocol.anthropic_models import (
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
    Message,
    ToolDefinition,
)
from gateway.protocol.openai_models import (
    OpenAIChatCompletionChunk,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIChoice,
    OpenAIChoiceMessage,
    OpenAIChunkChoice,
    OpenAIDelta,
    OpenAIUsage,
)


def convert_openai_to_anthropic(req: OpenAIChatCompletionRequest) -> AnthropicMessagesRequest:
    """Convert an OpenAI ChatCompletion request to an AnthropicMessagesRequest."""
    system_prompts: List[str] = []
    anthropic_messages: List[Message] = []

    for msg in req.messages:
        role = msg.role.lower()
        if role in ("system", "developer"):
            content = msg.content
            if isinstance(content, str):
                system_prompts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        system_prompts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        system_prompts.append(item)
        elif role == "tool":
            # Map tool result
            anthropic_messages.append(
                Message(
                    role="user",
                    content=[
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id or "tool_call_0",
                            "content": msg.content or "",
                        }
                    ],
                )
            )
        else:
            mapped_role = "assistant" if role == "assistant" else "user"
            content_blocks = []

            # Check if assistant made tool_calls
            if role == "assistant" and msg.tool_calls:
                if msg.content:
                    content_blocks.append({"type": "text", "text": str(msg.content)})
                for tc in msg.tool_calls:
                    fn = tc.get("function", {})
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except Exception:
                        args = {"raw_args": args_str}

                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "name": fn.get("name", "tool"),
                        "input": args,
                    })
                anthropic_messages.append(Message(role="assistant", content=content_blocks))
            else:
                anthropic_messages.append(Message(role=mapped_role, content=msg.content or ""))

    # Convert tools
    tools: Optional[List[ToolDefinition]] = None
    if req.tools:
        tools = []
        for t in req.tools:
            if t.get("type") == "function" and "function" in t:
                fn = t["function"]
                tools.append(
                    ToolDefinition(
                        name=fn.get("name", ""),
                        description=fn.get("description", ""),
                        input_schema=fn.get("parameters", {"type": "object", "properties": {}}),
                    )
                )

    system_text = "\n\n".join(system_prompts) if system_prompts else None
    max_tokens = req.max_completion_tokens or req.max_tokens or 4096

    # Stop sequences
    stop_seqs: Optional[List[str]] = None
    if isinstance(req.stop, str):
        stop_seqs = [req.stop]
    elif isinstance(req.stop, list):
        stop_seqs = req.stop

    return AnthropicMessagesRequest(
        model=req.model,
        messages=anthropic_messages,
        system=system_text,
        max_tokens=max_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
        stop_sequences=stop_seqs,
        stream=bool(req.stream),
        tools=tools,
    )


def convert_anthropic_to_openai_response(
    anthropic_resp: AnthropicMessagesResponse,
) -> OpenAIChatCompletionResponse:
    """Convert an AnthropicMessagesResponse to an OpenAIChatCompletionResponse."""
    text_content = ""
    tool_calls: List[Dict[str, Any]] = []

    for block in anthropic_resp.content:
        if isinstance(block, dict):
            b_type = block.get("type")
            if b_type == "text":
                text_content += block.get("text", "")
            elif b_type == "tool_use":
                tool_calls.append({
                    "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                    "type": "function",
                    "function": {
                        "name": block.get("name", "tool"),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })
        else:
            b_type = getattr(block, "type", None)
            if b_type == "text":
                text_content += getattr(block, "text", "")
            elif b_type == "tool_use":
                tool_calls.append({
                    "id": getattr(block, "id", f"call_{uuid.uuid4().hex[:8]}"),
                    "type": "function",
                    "function": {
                        "name": getattr(block, "name", "tool"),
                        "arguments": json.dumps(getattr(block, "input", {})),
                    },
                })

    choice_msg = OpenAIChoiceMessage(
        role="assistant",
        content=text_content if text_content or not tool_calls else None,
        tool_calls=tool_calls if tool_calls else None,
    )

    finish_reason = "tool_calls" if tool_calls else "stop"

    return OpenAIChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        object="chat.completion",
        created=int(time.time()),
        model=anthropic_resp.model,
        choices=[
            OpenAIChoice(
                index=0,
                message=choice_msg,
                finish_reason=finish_reason,
            )
        ],
        usage=OpenAIUsage(
            prompt_tokens=anthropic_resp.usage.input_tokens,
            completion_tokens=anthropic_resp.usage.output_tokens,
            total_tokens=anthropic_resp.usage.input_tokens + anthropic_resp.usage.output_tokens,
        ),
    )


async def transform_anthropic_sse_to_openai(
    anthropic_sse_stream: AsyncGenerator[str, None],
    requested_model: str,
) -> AsyncGenerator[str, None]:
    """Transform Anthropic SSE event stream into OpenAI format SSE chunks."""
    cmpl_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    # Send initial role delta
    init_chunk = OpenAIChatCompletionChunk(
        id=cmpl_id,
        created=created,
        model=requested_model,
        choices=[OpenAIChunkChoice(index=0, delta=OpenAIDelta(role="assistant"), finish_reason=None)],
    )
    yield f"data: {init_chunk.model_dump_json()}\n\n"

    async for sse_event in anthropic_sse_stream:
        # Parse SSE line
        for line in sse_event.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue

            json_str = line[5:].strip()
            if not json_str:
                continue

            try:
                payload = json.loads(json_str)
                p_type = payload.get("type")

                if p_type == "content_block_delta":
                    delta = payload.get("delta", {})
                    d_type = delta.get("type")
                    if d_type == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            chunk = OpenAIChatCompletionChunk(
                                id=cmpl_id,
                                created=created,
                                model=requested_model,
                                choices=[
                                    OpenAIChunkChoice(
                                        index=0,
                                        delta=OpenAIDelta(content=text),
                                        finish_reason=None,
                                    )
                                ],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                    elif d_type == "input_json_delta":
                        partial_json = delta.get("partial_json", "")
                        if partial_json:
                            chunk = OpenAIChatCompletionChunk(
                                id=cmpl_id,
                                created=created,
                                model=requested_model,
                                choices=[
                                    OpenAIChunkChoice(
                                        index=0,
                                        delta=OpenAIDelta(
                                            tool_calls=[
                                                {
                                                    "index": 0,
                                                    "function": {"arguments": partial_json},
                                                }
                                            ]
                                        ),
                                        finish_reason=None,
                                    )
                                ],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                elif p_type == "content_block_start":
                    cb = payload.get("content_block", {})
                    if cb.get("type") == "tool_use":
                        chunk = OpenAIChatCompletionChunk(
                            id=cmpl_id,
                            created=created,
                            model=requested_model,
                            choices=[
                                OpenAIChunkChoice(
                                    index=0,
                                    delta=OpenAIDelta(
                                        tool_calls=[
                                            {
                                                "index": 0,
                                                "id": cb.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                                "type": "function",
                                                "function": {
                                                    "name": cb.get("name", "tool"),
                                                    "arguments": "",
                                                },
                                            }
                                        ]
                                    ),
                                    finish_reason=None,
                                )
                            ],
                        )
                        yield f"data: {chunk.model_dump_json()}\n\n"

                elif p_type == "message_stop":
                    final_chunk = OpenAIChatCompletionChunk(
                        id=cmpl_id,
                        created=created,
                        model=requested_model,
                        choices=[
                            OpenAIChunkChoice(
                                index=0,
                                delta=OpenAIDelta(),
                                finish_reason="stop",
                            )
                        ],
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"

            except Exception:
                continue
