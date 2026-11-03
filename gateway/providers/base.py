"""Base provider abstraction."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from gateway.protocol.anthropic_models import (
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
)


class BaseProvider(ABC):
    """Abstract inference provider interface."""

    @abstractmethod
    async def stream_messages(
        self, request: AnthropicMessagesRequest
    ) -> AsyncGenerator[str, None]:
        """Stream Anthropic SSE event strings."""
        pass

    @abstractmethod
    async def complete_messages(
        self, request: AnthropicMessagesRequest
    ) -> AnthropicMessagesResponse:
        """Non-streaming complete messages response."""
        pass
