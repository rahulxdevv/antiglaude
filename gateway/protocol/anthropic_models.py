"""Pydantic data models for Anthropic Messages API v1."""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: Optional[str] = ""
    input_schema: Dict[str, Any] = Field(default_factory=lambda: {"type": "object"})


class ThinkingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Optional[str] = "enabled"  # "enabled" or "adaptive"
    budget_tokens: Optional[int] = None


class TextContentBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageSource(BaseModel):
    type: str = "base64"
    media_type: str = "image/png"
    data: str


class ImageContentBlock(BaseModel):
    type: Literal["image"] = "image"
    source: ImageSource


class ToolUseContentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)
    thoughtSignature: Optional[str] = None


class ToolResultContentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Optional[Union[str, List[Dict[str, Any]]]] = ""
    is_error: Optional[bool] = False


class ThinkingContentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


ContentBlock = Union[
    TextContentBlock,
    ImageContentBlock,
    ToolUseContentBlock,
    ToolResultContentBlock,
    ThinkingContentBlock,
    Dict[str, Any],
]


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "user"
    content: Union[str, List[ContentBlock], Dict[str, Any], Any] = ""


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: List[Message]
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    max_tokens: int = 4096
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    stream: bool = False
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    thinking: Optional[ThinkingConfig] = None
    safeguards: Optional[Any] = None


class UsageMetadata(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class AnthropicMessagesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str
    content: List[ContentBlock]
    stop_reason: Optional[str] = "end_turn"
    stop_sequence: Optional[str] = None
    usage: UsageMetadata = Field(default_factory=UsageMetadata)
    safeguard_results: Optional[List[Dict[str, Any]]] = None


class ModelItem(BaseModel):
    id: str
    object: str = "model"
    created: int = 1700000000
    owned_by: str = "anthropic"
    display_name: Optional[str] = None
    description: Optional[str] = None


class ModelsResponse(BaseModel):
    data: List[ModelItem]
    has_more: bool = False
