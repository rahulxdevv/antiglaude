"""FastAPI server implementing the Anthropic Messages Gateway API."""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.auth.project_resolver import project_resolver
from gateway.auth.token_manager import token_manager
from gateway.config import DEFAULT_CONFIG
from gateway.protocol.anthropic_models import (
    AnthropicMessagesRequest,
    AnthropicMessagesResponse,
    ModelItem,
    ModelsResponse,
)
from gateway.providers.cloudcode_provider import cloudcode_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway.server")

app = FastAPI(
    title="Antiglaude Bridge Gateway",
    description="Anthropic Messages compatible gateway for Google Gemini / Cloud Code inference backends",
    version="1.0.0",
)

# Enable CORS for local dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint with provider status."""
    try:
        token = await token_manager.get_access_token()
        proj, tier = await project_resolver.resolve(token)
        return {
            "status": "healthy",
            "account": token_manager.account_email,
            "project_id": proj,
            "tier": tier,
            "timestamp": int(time.time()),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": int(time.time()),
        }


@app.get("/v1/models")
async def list_models(
    limit: Optional[int] = Query(default=1000),
    before_id: Optional[str] = None,
    after_id: Optional[str] = None,
) -> ModelsResponse:
    """List available models in Anthropic format."""
    # List of models supported by Cloud Code and mapped in the gateway
    models = [
        ModelItem(
            id="claude-sonnet-4-6",
            display_name="Claude Sonnet 4.6 (Thinking)",
            created=1738000000,
        ),
        ModelItem(
            id="claude-opus-4-6-thinking",
            display_name="Claude Opus 4.6 (Thinking)",
            created=1738000000,
        ),
        ModelItem(
            id="claude-3-7-sonnet-20250219",
            display_name="Claude 3.7 Sonnet (Alias)",
            created=1738000000,
        ),
        ModelItem(
            id="claude-3-5-sonnet-20241022",
            display_name="Claude 3.5 Sonnet (Alias)",
            created=1738000000,
        ),
        ModelItem(
            id="gemini-3-flash",
            display_name="Gemini 3 Flash",
            created=1738000000,
        ),
        ModelItem(
            id="gemini-3.5-flash-lite",
            display_name="Gemini 3.5 Flash Lite",
            created=1738000000,
        ),
        ModelItem(
            id="gemini-2.5-pro",
            display_name="Gemini 2.5 Pro",
            created=1738000000,
        ),
    ]
    return ModelsResponse(data=models[:limit], has_more=False)


@app.post("/v1/messages")
async def create_message(
    request: AnthropicMessagesRequest,
    req_raw: Request,
    anthropic_version: Optional[str] = Header(default=None),
    anthropic_beta: Optional[str] = Header(default=None),
    x_claude_code_session_id: Optional[str] = Header(default=None),
):
    """Handle Anthropic Messages inference request."""
    logger.info(
        "Received /v1/messages request: model=%s, messages=%d, stream=%s, tools=%d",
        request.model,
        len(request.messages),
        request.stream,
        len(request.tools) if request.tools else 0,
    )

    try:
        if request.stream:
            # Return SSE stream
            async def event_generator():
                async for event in cloudcode_provider.stream_messages(request):
                    yield event

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream; charset=utf-8",
                },
            )
        else:
            # Non-streaming response
            response = await cloudcode_provider.complete_messages(request)
            return JSONResponse(content=response.model_dump())

    except Exception as e:
        logger.exception("Error processing /v1/messages: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"type": "api_error", "message": str(e)},
        )


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: AnthropicMessagesRequest):
    """Token counting endpoint."""
    total_chars = 0
    if request.system:
        if isinstance(request.system, str):
            total_chars += len(request.system)
        elif isinstance(request.system, list):
            for b in request.system:
                if isinstance(b, dict):
                    total_chars += len(b.get("text", ""))

    for msg in request.messages:
        if isinstance(msg.content, str):
            total_chars += len(msg.content)
        elif isinstance(msg.content, list):
            for b in msg.content:
                if isinstance(b, dict):
                    total_chars += len(b.get("text", ""))
                    total_chars += len(b.get("thinking", ""))
                    if "input" in b:
                        total_chars += len(str(b["input"]))

    # 1 token ~= 4 chars heuristic for token counting endpoint
    estimated_tokens = max(1, total_chars // 4)
    return {"input_tokens": estimated_tokens}


def start_server():
    """CLI launcher for uvicorn server."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Antiglaude Bridge Gateway")
    parser.add_argument("--host", default=DEFAULT_CONFIG.host, help="Host to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_CONFIG.port, help="Port to bind")
    args = parser.parse_args()

    print(f"Starting Antiglaude Bridge on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    start_server()
