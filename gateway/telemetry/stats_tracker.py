"""Live telemetry, request logging, and quota tracker for Antiglaude Bridge."""

import json
import logging
import os
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("gateway.telemetry")

STATS_DIR = Path.home() / ".antiglaude"
STATS_FILE = STATS_DIR / "stats.json"


class StatsTracker:
    """Tracks live usage, token consumption, rate limits, and request histories."""

    def __init__(self, daily_limit: int = 1500):
        self.daily_limit = daily_limit
        self.total_requests = 0
        self.today_date = date.today().isoformat()
        self.requests_today = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.errors_count = 0
        self.models_usage: Dict[str, int] = {}
        self.recent_requests: Deque[Dict[str, Any]] = deque(maxlen=30)
        self.server_start_time = time.time()

        # Cached upstream tier details
        self.account_email: Optional[str] = None
        self.project_id: Optional[str] = None
        self.tier_id: str = "g1-pro-tier"
        self.tier_name: str = "Google AI Pro"
        self.upgrade_text: Optional[str] = None
        self.available_credits: List[Dict[str, Any]] = []

        self._load_persisted()

    def _load_persisted(self):
        """Load persisted counters from ~/.antiglaude/stats.json."""
        try:
            if STATS_FILE.exists():
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.total_requests = data.get("total_requests", 0)
                    self.total_input_tokens = data.get("total_input_tokens", 0)
                    self.total_output_tokens = data.get("total_output_tokens", 0)
                    self.errors_count = data.get("errors_count", 0)
                    self.models_usage = data.get("models_usage", {})

                    saved_date = data.get("today_date")
                    if saved_date == self.today_date:
                        self.requests_today = data.get("requests_today", 0)
                    else:
                        self.requests_today = 0
        except Exception as e:
            logger.debug("Failed loading stats file: %s", e)

    def _persist(self):
        """Save current counters to disk."""
        try:
            STATS_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "today_date": self.today_date,
                "total_requests": self.total_requests,
                "requests_today": self.requests_today,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "errors_count": self.errors_count,
                "models_usage": self.models_usage,
                "last_updated": time.time(),
            }
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug("Failed persisting stats file: %s", e)

    def _check_midnight_reset(self):
        """Reset today's counters if the day rolled over."""
        current_date = date.today().isoformat()
        if current_date != self.today_date:
            self.today_date = current_date
            self.requests_today = 0

    def record_request(
        self,
        endpoint: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        status_code: int = 200,
        stream: bool = False,
        client: str = "claude-code",
    ):
        """Record an inference turn and update counters."""
        self._check_midnight_reset()

        self.total_requests += 1
        self.requests_today += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        if status_code >= 400:
            self.errors_count += 1

        # Track model counts
        self.models_usage[model] = self.models_usage.get(model, 0) + 1

        # Add to recent requests
        entry = {
            "id": f"req-{self.total_requests}",
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%H:%M:%S"),
            "endpoint": endpoint,
            "model": model,
            "status_code": status_code,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "latency_ms": round(latency_ms, 1),
            "stream": stream,
            "client": client,
        }
        self.recent_requests.append(entry)

        # Periodically persist
        if self.total_requests % 5 == 0:
            self._persist()

    def update_quota_info(
        self,
        account_email: Optional[str] = None,
        project_id: Optional[str] = None,
        tier_id: Optional[str] = None,
        tier_name: Optional[str] = None,
        upgrade_text: Optional[str] = None,
        available_credits: Optional[List[Dict[str, Any]]] = None,
    ):
        """Update cached upstream account and quota information."""
        if account_email:
            self.account_email = account_email
        if project_id:
            self.project_id = project_id
        if tier_id:
            self.tier_id = tier_id
        if tier_name:
            self.tier_name = tier_name
        if upgrade_text:
            self.upgrade_text = upgrade_text
        if available_credits is not None:
            self.available_credits = available_credits

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a complete real-time telemetry snapshot."""
        self._check_midnight_reset()
        requests_remaining = max(0, self.daily_limit - self.requests_today)
        quota_percent_used = round((self.requests_today / max(1, self.daily_limit)) * 100.0, 1)

        return {
            "uptime_seconds": int(time.time() - self.server_start_time),
            "total_requests": self.total_requests,
            "requests_today": self.requests_today,
            "daily_limit": self.daily_limit,
            "requests_remaining": requests_remaining,
            "quota_percent_used": quota_percent_used,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "errors_count": self.errors_count,
            "models_usage": dict(self.models_usage),
            "account": {
                "email": self.account_email or "default@antigravity",
                "project_id": self.project_id or "aicode-consumers",
                "tier_id": self.tier_id,
                "tier_name": self.tier_name,
                "upgrade_text": self.upgrade_text,
                "available_credits": self.available_credits,
            },
            "recent_requests": list(self.recent_requests),
        }


# Singleton instance
stats_tracker = StatsTracker()
