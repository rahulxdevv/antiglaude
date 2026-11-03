"""Google Cloud Code upstream provider with streaming, token refresh, and keep-alive."""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

import httpx

from gateway.auth.project_resolver import project_resolver
from gateway.auth.token_manager import token_manager
from gateway.config import DEFAULT_CONFIG
from gateway.protocol.anthropic_models import (
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
    UsageMetadata,
)
from gateway.protocol.sse_events import ping_event
from gateway.providers.base import BaseProvider
from gateway.reliability.backoff import calculate_backoff, parse_retry_after
from gateway.translation.request_converter import convert_anthropic_to_cloudcode
from gateway.translation.response_converter import StreamParser

logger = logging.getLogger("gateway.cloudcode")


class CloudCodeProvider(BaseProvider):
    """Upstream inference provider using Google Cloud Code API."""

    def __init__(self, config=DEFAULT_CONFIG):
        self.config = config

    def _build_headers(self, access_token: str, model_name: str, session_id: str) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "antigravity/hub/1.107.0 darwin/arm64",
            "X-Client-Name": "antigravity",
            "X-Client-Version": "1.107.0",
            "x-goog-api-client": "gl-node/18.18.2 fire/0.8.6 grpc/1.10.x",
            "X-Machine-Session-Id": session_id,
        }
        # Interleaved thinking header for Claude models
        if "claude" in model_name.lower():
            headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"
        return headers

    async def stream_messages(
        self,
        request: AnthropicMessagesRequest,
        parser: Optional[StreamParser] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream Anthropic SSE events from Google Cloud Code."""
        token = await token_manager.get_access_token()
        project_id, tier = await project_resolver.resolve(token)

        payload = convert_anthropic_to_cloudcode(
            request,
            project_id=project_id,
            account_email=token_manager.account_email,
            config=self.config,
        )

        canonical_model = payload["model"]
        session_id = payload["request"].get("sessionId", "session-default")
        headers = self._build_headers(token, canonical_model, session_id)

        endpoints = [
            f"{self.config.cloudcode_endpoints[0]}/v1internal:streamGenerateContent?alt=sse",
            f"{self.config.cloudcode_endpoints[1]}/v1internal:streamGenerateContent?alt=sse",
        ]

        if parser is None:
            parser = StreamParser(requested_model=request.model)

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            for endpoint_url in endpoints:
                try:
                    logger.debug("Requesting %s (attempt %d)", endpoint_url, attempt + 1)
                    timeout = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=30.0)

                    async with httpx.AsyncClient(timeout=timeout) as client:
                        async with client.stream(
                            "POST",
                            endpoint_url,
                            headers=headers,
                            json=payload,
                        ) as response:
                            if response.status_code == 401:
                                logger.warning("Received 401 UNAUTHENTICATED, refreshing token...")
                                token = await token_manager.get_access_token()
                                headers["Authorization"] = f"Bearer {token}"
                                continue

                            if response.status_code == 429:
                                err_text = await response.aread()
                                wait_sec = parse_retry_after(err_text.decode("utf-8", errors="ignore"))
                                logger.warning("Received 429 RESOURCE_EXHAUSTED, waiting %.1fs", wait_sec)
                                await asyncio.sleep(wait_sec)
                                continue

                            if response.status_code != 200:
                                err_body = await response.aread()
                                err_msg = err_body.decode("utf-8", errors="ignore")[:300]
                                logger.error("Upstream error %d: %s", response.status_code, err_msg)
                                last_error = RuntimeError(f"Upstream returned {response.status_code}: {err_msg}")
                                continue

                            # Stream active!
                            last_event_time = asyncio.get_event_loop().time()

                            async for line in response.aiter_lines():
                                if not line:
                                    continue

                                # Periodic keep-alive ping if needed
                                now = asyncio.get_event_loop().time()
                                if now - last_event_time > 15.0:
                                    yield ping_event()
                                    last_event_time = now

                                sse_events = parser.parse_chunk(line)
                                for ev in sse_events:
                                    yield ev
                                    last_event_time = asyncio.get_event_loop().time()

                            # Stream completed cleanly from upstream
                            for ev in parser.finalize():
                                yield ev
                            return

                except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                    last_error = e
                    logger.warning("Stream network error on %s: %s", endpoint_url, e)

            # Backoff before retrying attempt
            backoff_sec = calculate_backoff(attempt)
            logger.info("Retrying stream in %.2fs (attempt %d/%d)", backoff_sec, attempt + 1, max_retries)
            await asyncio.sleep(backoff_sec)

        raise last_error or RuntimeError("Failed to complete stream after retries")

    async def complete_messages(
        self, request: AnthropicMessagesRequest
    ) -> AnthropicMessagesResponse:
        """Accumulate stream into non-streaming AnthropicMessagesResponse."""
        parser = StreamParser(requested_model=request.model)
        async for _ in self.stream_messages(request, parser=parser):
            pass

        return AnthropicMessagesResponse(
            id=parser.message_id,
            model=request.model,
            content=parser.accumulated_content,
            stop_reason=parser.stop_reason or "end_turn",
            usage=UsageMetadata(
                input_tokens=parser.input_tokens,
                output_tokens=parser.output_tokens,
                cache_read_input_tokens=parser.cache_read_tokens,
            ),
        )


cloudcode_provider = CloudCodeProvider()

