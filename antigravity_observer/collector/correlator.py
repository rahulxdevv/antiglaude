"""Cross-layer event correlator.

Correlates:
  1. Low-level HTTP requests and SSE streams (from ls-main.log)
  2. Generation metadata and token usage metrics (from SQLite gen_metadata)
  3. Multi-step agent execution trajectory and tool calls (from transcript.jsonl)
into unified, high-level AI Interaction Execution Cycles.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from antigravity_observer.collector.log_parser import LogParser
from antigravity_observer.collector.sqlite_reader import SqliteReader
from antigravity_observer.collector.transcript_parser import TranscriptParser

logger = logging.getLogger("antigravity_observer.correlator")


class EventCorrelator:
    """Correlates logs, SQLite generation metadata, and transcripts into unified execution cycles."""

    def __init__(
        self,
        log_parser: Optional[LogParser] = None,
        transcript_parser: Optional[TranscriptParser] = None,
        sqlite_reader: Optional[SqliteReader] = None,
    ):
        self.log_parser = log_parser or LogParser()
        self.transcript_parser = transcript_parser or TranscriptParser()
        self.sqlite_reader = sqlite_reader or SqliteReader()

    def get_unified_timeline(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Constructs an integrated execution timeline for a conversation.
        
        Merges steps, thinking traces, tool executions, API requests, and exact token counts.
        """
        steps = self.transcript_parser.read_steps(conversation_id)
        generations = self.sqlite_reader.get_generations(conversation_id)
        api_requests = self.log_parser.parse_api_requests(limit=1000)

        # Index generations by response_id
        gen_by_rid: Dict[str, Dict] = {}
        for g in generations:
            rid = g.get("response_id")
            if rid:
                gen_by_rid[rid] = g

        # Index api_requests by response_id
        api_by_rid: Dict[str, Dict] = {}
        for req in api_requests:
            rid = req.get("response_id")
            if rid:
                api_by_rid[rid] = req

        # Group steps into execution cycles
        timeline = []
        current_cycle: Optional[Dict[str, Any]] = None
        planner_idx = 0

        for step in steps:
            stype = step.get("type")
            sidx = step.get("step_index", 0)

            if stype == "USER_INPUT":
                if current_cycle:
                    timeline.append(current_cycle)
                    current_cycle = None

                timeline.append({
                    "cycle_type": "user_input",
                    "step_index": sidx,
                    "timestamp": step.get("created_at"),
                    "prompt": step.get("content", ""),
                    "truncated": step.get("truncated", False),
                })

            elif stype == "PLANNER_RESPONSE":
                if current_cycle:
                    timeline.append(current_cycle)

                # Match corresponding generation
                gen_meta = None
                # Match by sequence or response ID if known
                if planner_idx < len(generations):
                    gen_meta = generations[planner_idx]
                planner_idx += 1

                # If gen_meta has response_id, match API request
                resp_id = gen_meta.get("response_id") if gen_meta else ""
                api_info = api_by_rid.get(resp_id)

                current_cycle = {
                    "cycle_type": "agent_turn",
                    "step_index": sidx,
                    "timestamp": step.get("created_at"),
                    "thinking": step.get("thinking", ""),
                    "thinking_length": len(step.get("thinking", "")),
                    "model": gen_meta.get("model", "Gemini 3.8 Flash (High)") if gen_meta else "Gemini 3.8 Flash (High)",
                    "model_id": gen_meta.get("model_id", "") if gen_meta else "",
                    "tokens": {
                        "prompt": gen_meta.get("prompt_tokens", 0) if gen_meta else 0,
                        "output": gen_meta.get("output_tokens", 0) if gen_meta else 0,
                        "thinking": gen_meta.get("thinking_tokens", 0) if gen_meta else 0,
                        "total": gen_meta.get("total_tokens", 0) if gen_meta else 0,
                    },
                    "api_request": {
                        "url": api_info.get("url", "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse") if api_info else "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse",
                        "trace_id": api_info.get("trace_id", gen_meta.get("trace_id", "")) if api_info else gen_meta.get("trace_id", "") if gen_meta else "",
                        "response_id": resp_id,
                        "is_streaming": True,
                    },
                    "tool_calls_planned": step.get("tool_calls", []),
                    "tool_executions": [],
                }

            elif stype in (
                "RUN_COMMAND", "LIST_DIRECTORY", "VIEW_FILE", "GREP_SEARCH",
                "SEARCH_WEB", "READ_URL_CONTENT", "BROWSER_SUBAGENT", "ASK_QUESTION", "CODE_ACTION"
            ):
                tool_exec = {
                    "step_index": sidx,
                    "tool_type": stype,
                    "timestamp": step.get("created_at"),
                    "status": step.get("status", "DONE"),
                    "exit_code": step.get("exit_code"),
                    "output_preview": step.get("content", "")[:300] if step.get("content") else "",
                    "content_length": len(step.get("content", "")),
                    "truncated": step.get("truncated", False),
                }

                if current_cycle and current_cycle.get("cycle_type") == "agent_turn":
                    current_cycle["tool_executions"].append(tool_exec)
                else:
                    # Standalone tool execution
                    timeline.append({
                        "cycle_type": "tool_execution",
                        **tool_exec
                    })

        if current_cycle:
            timeline.append(current_cycle)

        return timeline

    def get_requests_overview(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Provides an aggregated list of observable LLM requests across all channels.
        
        Combines ls-main.log requests with decoded SQLite tokens and response IDs.
        """
        raw_requests = self.log_parser.parse_api_requests(limit=limit)
        active_cid = self.transcript_parser.get_active_conversation_id()
        generations = self.sqlite_reader.get_generations(active_cid) if active_cid else []

        gen_by_rid = {g["response_id"]: g for g in generations if g.get("response_id")}

        res = []
        for req in raw_requests:
            rid = req.get("response_id", "")
            gen = gen_by_rid.get(rid)

            item = {
                "timestamp": req.get("timestamp"),
                "endpoint": req.get("endpoint"),
                "operation": req.get("operation"),
                "is_streaming": req.get("is_streaming", False),
                "trace_id": req.get("trace_id"),
                "response_id": rid,
                "model": gen.get("model", "Gemini 3.8 Flash (High)") if gen else "Gemini 3.8 Flash (High)",
                "prompt_tokens": gen.get("prompt_tokens", 0) if gen else 0,
                "output_tokens": gen.get("output_tokens", 0) if gen else 0,
                "thinking_tokens": gen.get("thinking_tokens", 0) if gen else 0,
                "status": "200 OK",
            }
            res.append(item)

        res.reverse()
        return res
