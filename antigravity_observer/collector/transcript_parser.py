"""Transcript parser and conversation trajectory reader.

Reads transcript.jsonl and transcript_full.jsonl files from ~/.gemini/antigravity-ide/brain/<cid>/
to extract complete multi-step agent execution histories, thinking traces, tool calls, and outcomes.
"""

import glob
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("antigravity_observer.transcript_parser")


class TranscriptParser:
    """Reads and monitors Antigravity conversation transcripts."""

    def __init__(self, brain_base_dir: Optional[str] = None):
        if brain_base_dir:
            self.brain_base_dir = os.path.expanduser(brain_base_dir)
        else:
            self.brain_base_dir = os.path.expanduser("~/.gemini/antigravity-ide/brain")

    def list_conversations(self) -> List[Dict[str, Any]]:
        """Lists all conversations found in brain base directory with summary metadata."""
        if not os.path.exists(self.brain_base_dir):
            return []

        conversations = []
        for cid in os.listdir(self.brain_base_dir):
            cdir = os.path.join(self.brain_base_dir, cid)
            if not os.path.isdir(cdir):
                continue

            transcript_path = os.path.join(cdir, ".system_generated", "logs", "transcript.jsonl")
            if not os.path.exists(transcript_path):
                continue

            try:
                mtime = os.path.getmtime(transcript_path)
                size = os.path.getsize(transcript_path)
                mtime_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

                # Read first few lines for title and objective
                title, first_prompt, created_at, step_count = self._inspect_conversation_header(transcript_path)

                conversations.append({
                    "id": cid,
                    "title": title or f"Conversation {cid[:8]}",
                    "preview": first_prompt[:120] if first_prompt else "",
                    "created_at": created_at,
                    "last_modified": mtime_iso,
                    "mtime": mtime,
                    "step_count": step_count,
                    "file_size": size,
                    "transcript_path": transcript_path,
                })
            except Exception as e:
                logger.debug(f"Error reading conversation {cid}: {e}")

        # Sort by most recently modified first
        conversations.sort(key=lambda x: x["mtime"], reverse=True)
        return conversations

    def get_active_conversation_id(self) -> Optional[str]:
        """Identifies the conversation currently active or most recently modified."""
        convs = self.list_conversations()
        return convs[0]["id"] if convs else None

    def read_steps(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Reads parsed execution steps for a conversation from transcript.jsonl."""
        tpath = os.path.join(self.brain_base_dir, conversation_id, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.exists(tpath):
            return []

        steps = []
        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        step_data = json.loads(line)
                        steps.append(self._normalize_step(step_data))
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error reading transcript for {conversation_id}: {e}")

        if limit and len(steps) > limit:
            return steps[-limit:]
        return steps

    def get_conversation_metrics(self, conversation_id: str) -> Dict[str, Any]:
        """Aggregates execution timeline metrics, tool usage, and durations for a conversation."""
        steps = self.read_steps(conversation_id)
        if not steps:
            return {}

        tool_counts: Dict[str, int] = {}
        tool_durations: Dict[str, float] = {}
        total_thinking_chars = 0
        planner_count = 0
        error_count = 0
        user_input_count = 0

        first_time = None
        last_time = None

        for s in steps:
            stype = s.get("type", "")
            status = s.get("status", "")
            tstr = s.get("created_at")

            if tstr:
                try:
                    dt = datetime.fromisoformat(tstr.replace("Z", "+00:00"))
                    if first_time is None or dt < first_time:
                        first_time = dt
                    if last_time is None or dt > last_time:
                        last_time = dt
                except Exception:
                    pass

            if stype == "USER_INPUT":
                user_input_count += 1
            elif stype == "PLANNER_RESPONSE":
                planner_count += 1
                thinking = s.get("thinking", "")
                total_thinking_chars += len(thinking)
            elif status == "ERROR":
                error_count += 1

            for call in s.get("tool_calls", []):
                tname = call.get("name", "unknown")
                tool_counts[tname] = tool_counts.get(tname, 0) + 1

        duration_sec = 0.0
        if first_time and last_time:
            duration_sec = max(0.0, (last_time - first_time).total_seconds())

        return {
            "conversation_id": conversation_id,
            "total_steps": len(steps),
            "user_prompts": user_input_count,
            "planner_responses": planner_count,
            "tool_calls_total": sum(tool_counts.values()),
            "tool_breakdown": tool_counts,
            "error_count": error_count,
            "total_thinking_chars": total_thinking_chars,
            "started_at": first_time.isoformat() if first_time else "",
            "ended_at": last_time.isoformat() if last_time else "",
            "duration_seconds": duration_sec,
        }

    def _inspect_conversation_header(self, transcript_path: str) -> Tuple[str, str, str, int]:
        """Inspects first few lines of a transcript to extract title, initial prompt, and total lines."""
        title = ""
        first_prompt = ""
        created_at = ""
        step_count = 0

        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                step_count += 1
                if i < 10 and not title:
                    try:
                        data = json.loads(line)
                        if not created_at:
                            created_at = data.get("created_at", "")

                        content = data.get("content", "")
                        if data.get("type") == "USER_INPUT" and content:
                            if not first_prompt:
                                first_prompt = content.strip()
                            # Search for "Project: <Title>" or first sentence
                            m = re.search(r"Project:\s*([^\n\r]+)", content)
                            if m:
                                title = m.group(1).strip()
                            elif not title:
                                title = content.split("\n")[0][:60]
                        elif data.get("type") == "CONVERSATION_HISTORY" and content:
                            m = re.search(r"## Conversation [^:]+:\s*([^\n\r]+)", content)
                            if m and not title:
                                title = m.group(1).strip()
                    except Exception:
                        pass

        return title, first_prompt, created_at, step_count

    def _normalize_step(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures step dictionaries have standard format and fields."""
        return {
            "step_index": raw.get("step_index", 0),
            "source": raw.get("source", ""),
            "type": raw.get("type", "UNKNOWN"),
            "status": raw.get("status", "DONE"),
            "created_at": raw.get("created_at", ""),
            "thinking": raw.get("thinking", ""),
            "tool_calls": raw.get("tool_calls", []),
            "content": raw.get("content", ""),
            "exit_code": raw.get("exit_code"),
            "error": raw.get("error"),
            "truncated": "content" in raw.get("truncated_fields", []),
        }
