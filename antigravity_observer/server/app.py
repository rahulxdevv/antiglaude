"""FastAPI application serving Antigravity Observer REST API, SSE streaming, and Web UI."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from antigravity_observer.collector.correlator import EventCorrelator
from antigravity_observer.collector.log_parser import LogParser
from antigravity_observer.collector.process_detector import ProcessDetector
from antigravity_observer.collector.rpc_client import LanguageServerRpcClient
from antigravity_observer.collector.sqlite_reader import SqliteReader
from antigravity_observer.collector.transcript_parser import TranscriptParser
from antigravity_observer.server.export import DiagnosticExporter
from antigravity_observer.storage.observer_db import ObserverDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("antigravity_observer.app")

# Shared state singletons
detector = ProcessDetector()
log_parser = LogParser()
transcript_parser = TranscriptParser()
sqlite_reader = SqliteReader()
correlator = EventCorrelator(log_parser, transcript_parser, sqlite_reader)
storage = ObserverDatabase()
rpc_client: Optional[LanguageServerRpcClient] = None
current_runtime = detector.detect()

# Background live polling task
async def background_poller():
    global rpc_client, current_runtime
    while True:
        try:
            # 1. Update runtime detection if needed
            current_runtime = detector.detect()
            if current_runtime.rpc_available and current_runtime.rpc_port and current_runtime.csrf_token:
                if not rpc_client or rpc_client.port != current_runtime.rpc_port:
                    rpc_client = LanguageServerRpcClient(current_runtime.rpc_port, current_runtime.csrf_token)

            # 2. Record recent requests into storage
            active_cid = transcript_parser.get_active_conversation_id()
            requests = correlator.get_requests_overview(limit=50)
            for r in requests:
                r["conversation_id"] = active_cid or ""
                storage.record_request(r)

            # 3. If RPC connected, snapshot quota periodically
            if rpc_client:
                try:
                    q_status = rpc_client.get_comprehensive_status()
                    if q_status.get("is_connected"):
                        storage.record_quota_snapshot(q_status)
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Background polling tick error: {e}")

        await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background_poller())
    yield
    task.cancel()


app = FastAPI(
    title="Antigravity Observer",
    description="Developer Observability & Diagnostics Platform for Antigravity AI Workflows",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
async def get_status():
    """Returns runtime state, IDE connection, language server status, and active conversation."""
    global current_runtime
    active_cid = transcript_parser.get_active_conversation_id()
    return {
        "runtime": current_runtime.to_dict(),
        "active_conversation_id": active_cid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/quota")
async def get_quota():
    """Fetches real-time quota status, models, and buckets directly from language server RPC."""
    global rpc_client, current_runtime
    if not rpc_client or not current_runtime.rpc_available:
        current_runtime = detector.detect()
        if current_runtime.rpc_available and current_runtime.rpc_port and current_runtime.csrf_token:
            rpc_client = LanguageServerRpcClient(current_runtime.rpc_port, current_runtime.csrf_token)

    if rpc_client:
        try:
            return rpc_client.get_comprehensive_status()
        except Exception as e:
            logger.warning(f"Failed to fetch live quota from RPC: {e}")

    # Fallback to empty/offline status
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_connected": False,
        "message": "Language server RPC not connected or certificate error",
        "user": {},
        "prompt_credits": None,
        "models": [],
        "quota_groups": [],
    }


@app.get("/api/conversations")
async def list_conversations():
    """Lists all available conversations with metadata and token aggregates."""
    convs = transcript_parser.list_conversations()
    for c in convs:
        cid = c["id"]
        # Merge tokens from SQLite
        tokens_info = sqlite_reader.get_aggregate_tokens(cid)
        c.update(tokens_info)
    return convs


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Retrieves full conversation details, execution timeline, and step breakdown."""
    meta = transcript_parser.get_conversation_metrics(conversation_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tokens_info = sqlite_reader.get_aggregate_tokens(conversation_id)
    meta.update(tokens_info)

    timeline = correlator.get_unified_timeline(conversation_id)
    return {
        "metrics": meta,
        "timeline": timeline,
    }


@app.get("/api/requests")
async def list_requests(
    limit: int = Query(default=100, ge=1, le=500),
    query: Optional[str] = Query(default=None)
):
    """Lists recent observed LLM API requests with trace IDs, tokens, and model details."""
    if query:
        return storage.get_recent_requests(limit=limit, query=query)
    return correlator.get_requests_overview(limit=limit)


@app.get("/api/analytics")
async def get_analytics():
    """Returns aggregated performance, model usage distribution, and token counts."""
    # 1. Base storage analytics
    analytics = storage.get_analytics_summary()

    # 2. Enrich with active conversation metrics
    active_cid = transcript_parser.get_active_conversation_id()
    if active_cid:
        conv_metrics = transcript_parser.get_conversation_metrics(active_cid)
        token_info = sqlite_reader.get_aggregate_tokens(active_cid)
        analytics["active_conversation"] = {
            "id": active_cid,
            "metrics": conv_metrics,
            "tokens": token_info,
        }

    return analytics


@app.get("/api/events/live")
async def live_events_stream():
    """Server-Sent Events (SSE) stream pushing real-time interaction updates to dashboard."""
    async def event_generator():
        while True:
            try:
                active_cid = transcript_parser.get_active_conversation_id()
                recent_requests = correlator.get_requests_overview(limit=10)
                data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "active_conversation_id": active_cid,
                    "recent_requests": recent_requests,
                }
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                logger.debug(f"SSE generator tick error: {e}")
            await asyncio.sleep(2.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/export/json")
async def export_json_bundle(conversation_id: Optional[str] = None):
    """Exports diagnostic records as a downloadable JSON archive."""
    cid = conversation_id or transcript_parser.get_active_conversation_id()
    if not cid:
        raise HTTPException(status_code=400, detail="No conversation found to export")

    runtime = detector.detect().to_dict()
    quota = rpc_client.get_comprehensive_status() if rpc_client else {}
    conv_meta = transcript_parser.get_conversation_metrics(cid)
    conv_tokens = sqlite_reader.get_aggregate_tokens(cid)
    conv_meta.update(conv_tokens)

    timeline = correlator.get_unified_timeline(cid)
    requests = correlator.get_requests_overview(limit=200)
    analytics = storage.get_analytics_summary()

    json_str = DiagnosticExporter.export_json(runtime, quota, conv_meta, timeline, requests, analytics)
    filename = f"antigravity_diagnostic_{cid[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/export/markdown")
async def export_markdown_report(conversation_id: Optional[str] = None):
    """Exports diagnostic records as a formatted Markdown engineering report."""
    cid = conversation_id or transcript_parser.get_active_conversation_id()
    if not cid:
        raise HTTPException(status_code=400, detail="No conversation found to export")

    runtime = detector.detect().to_dict()
    quota = rpc_client.get_comprehensive_status() if rpc_client else {}
    conv_meta = transcript_parser.get_conversation_metrics(cid)
    conv_tokens = sqlite_reader.get_aggregate_tokens(cid)
    conv_meta.update(conv_tokens)

    timeline = correlator.get_unified_timeline(cid)
    analytics = storage.get_analytics_summary()

    md_str = DiagnosticExporter.export_markdown_report(runtime, quota, conv_meta, timeline, analytics)
    filename = f"antigravity_report_{cid[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    return Response(
        content=md_str,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# Serve Static UI files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
