"""Antigravity IDE log parser and stream tailer.

Parses ls-main.log, cloudcode.log, and Antigravity Quota.log to extract real-time API requests,
trace IDs, response IDs, timestamps, endpoints, errors, and quota updates.
"""

import glob
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, Generator, List, Optional

logger = logging.getLogger("antigravity_observer.log_parser")


class LogParser:
    """Parses and streams Antigravity IDE application and language server logs."""

    def __init__(self, logs_base_dir: Optional[str] = None):
        if logs_base_dir:
            self.logs_base_dir = os.path.expanduser(logs_base_dir)
        else:
            self.logs_base_dir = os.path.expanduser("~/Library/Application Support/Antigravity IDE/logs")

        # Regex patterns
        self.api_call_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+\[(.*?)\]\s+.*?"
            r"URL:\s+(\S+)\s+Trace:\s+(\S+)(?:\s+ResponseID:\s+(\S+))?"
        )
        self.cloudcode_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+\[(.*?)\]\s+\[CloudCode\]\s+POST\s+(\S+)\s+traceId:\s+(\S+)"
        )
        self.error_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+\[error\]\s+\[LS Main stderr\]\s+ERROR:.*?E\d{4}\s+[\d:.]+\s+\d+\s+([^:]+:\d+)]\s+(.*)"
        )

    def find_latest_session_dir(self) -> Optional[str]:
        """Finds the most recent IDE log session directory."""
        if not os.path.exists(self.logs_base_dir):
            return None
        dirs = [
            os.path.join(self.logs_base_dir, d)
            for d in os.listdir(self.logs_base_dir)
            if os.path.isdir(os.path.join(self.logs_base_dir, d)) and re.match(r"^\d{8}T\d{6}$", d)
        ]
        if not dirs:
            return None
        dirs.sort(key=lambda d: os.path.getmtime(d), reverse=True)
        return dirs[0]

    def get_log_paths(self, session_dir: Optional[str] = None) -> Dict[str, Optional[str]]:
        """Resolves active log file paths for a session."""
        sdir = session_dir or self.find_latest_session_dir()
        if not sdir:
            return {"ls_main": None, "cloudcode": None, "quota": None}

        ls_main = os.path.join(sdir, "ls-main.log")
        cloudcode = os.path.join(sdir, "cloudcode.log")

        # Find Quota log in window*/exthost/output_logging_*/2-Antigravity Quota.log
        quota_logs = glob.glob(os.path.join(sdir, "window*", "exthost", "output_logging_*", "*Quota.log"))
        quota_log = quota_logs[0] if quota_logs else None

        return {
            "session_dir": sdir,
            "ls_main": ls_main if os.path.exists(ls_main) else None,
            "cloudcode": cloudcode if os.path.exists(cloudcode) else None,
            "quota": quota_log if quota_log and os.path.exists(quota_log) else None,
        }

    def parse_api_requests(self, limit: int = 500, session_dir: Optional[str] = None) -> List[Dict]:
        """Parses recent API requests from ls-main.log."""
        paths = self.get_log_paths(session_dir)
        ls_path = paths["ls_main"]
        if not ls_path or not os.path.exists(ls_path):
            return []

        entries = []
        try:
            with open(ls_path, "r", encoding="utf-8", errors="ignore") as f:
                # Read all lines
                for line in f:
                    m = self.api_call_pattern.search(line)
                    if m:
                        timestamp_str = m.group(1)
                        log_level = m.group(2)
                        url = m.group(3)
                        trace_id = m.group(4)
                        response_id = m.group(5) or ""

                        # Extract endpoint name
                        endpoint = url.split("?")[0]
                        operation = endpoint.split(":")[-1] if ":" in endpoint else endpoint.split("/")[-1]
                        is_streaming = "alt=sse" in url

                        entries.append({
                            "timestamp": timestamp_str,
                            "url": url,
                            "endpoint": endpoint,
                            "operation": operation,
                            "is_streaming": is_streaming,
                            "trace_id": trace_id,
                            "response_id": response_id,
                            "level": log_level,
                            "source": "ls-main.log",
                        })
        except Exception as e:
            logger.error(f"Error parsing {ls_path}: {e}")

        # Return latest entries up to limit
        return entries[-limit:]

    def parse_system_errors(self, limit: int = 100, session_dir: Optional[str] = None) -> List[Dict]:
        """Extracts language server internal errors and warnings."""
        paths = self.get_log_paths(session_dir)
        ls_path = paths["ls_main"]
        if not ls_path or not os.path.exists(ls_path):
            return []

        errors = []
        try:
            with open(ls_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = self.error_pattern.search(line)
                    if m:
                        errors.append({
                            "timestamp": m.group(1),
                            "source_file": m.group(2),
                            "message": m.group(3).strip(),
                        })
        except Exception as e:
            logger.error(f"Error parsing errors from {ls_path}: {e}")

        return errors[-limit:]

    def tail_new_api_requests(self, last_file_pos: int = 0) -> Generator[Dict, None, int]:
        """Yields new API request entries written to ls-main.log since last_file_pos.
        
        Returns the new file position at the end.
        """
        paths = self.get_log_paths()
        ls_path = paths["ls_main"]
        if not ls_path or not os.path.exists(ls_path):
            return 0

        try:
            with open(ls_path, "r", encoding="utf-8", errors="ignore") as f:
                if last_file_pos > 0:
                    f.seek(last_file_pos)
                while True:
                    line = f.readline()
                    if not line:
                        break
                    m = self.api_call_pattern.search(line)
                    if m:
                        url = m.group(3)
                        yield {
                            "timestamp": m.group(1),
                            "url": url,
                            "endpoint": url.split("?")[0],
                            "operation": url.split(":")[-1].split("?")[0],
                            "is_streaming": "alt=sse" in url,
                            "trace_id": m.group(4),
                            "response_id": m.group(5) or "",
                        }
                return f.tell()
        except Exception as e:
            logger.debug(f"Error tailing log: {e}")
            return last_file_pos
