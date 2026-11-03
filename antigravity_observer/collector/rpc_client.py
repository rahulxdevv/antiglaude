"""Language Server HTTPS Connect-RPC Client.

Connects to the local Antigravity Language Server RPC endpoint using HTTPS and the Connect protocol.
Queries GetUserStatus and RetrieveUserQuotaSummary to retrieve live account info, quota limits,
remaining fractions, reset countdowns, and model configurations.
"""

import json
import logging
import ssl
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("antigravity_observer.rpc_client")


class LanguageServerRpcClient:
    """Client for querying the Antigravity Language Server HTTPS Connect RPC."""

    def __init__(self, port: int, csrf_token: str):
        self.port = port
        self.csrf_token = csrf_token
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def request(self, path: str, body: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Dict[str, Any]:
        """Performs a POST request to a Language Server Connect RPC endpoint."""
        url = f"https://127.0.0.1:{self.port}{path}"
        payload = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Codeium-Csrf-Token": self.csrf_token,
                "Connect-Protocol-Version": "1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=timeout) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"RPC call to {path} failed: {e}")
            raise

    def get_user_status(self) -> Dict[str, Any]:
        """Calls /exa.language_server_pb.LanguageServerService/GetUserStatus."""
        return self.request("/exa.language_server_pb.LanguageServerService/GetUserStatus")

    def get_quota_summary(self) -> Dict[str, Any]:
        """Calls /exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary."""
        return self.request("/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary", {"metadata": {}})

    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Aggregates user status, prompt credits, models, and quota buckets into a clean dict."""
        res = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": {},
            "prompt_credits": None,
            "models": [],
            "quota_groups": [],
            "is_connected": True,
        }

        # 1. Fetch GetUserStatus
        try:
            raw_status = self.get_user_status()
            ustatus = raw_status.get("userStatus", {})
            res["user"] = {
                "name": ustatus.get("name", "Unknown"),
                "email": ustatus.get("email", ""),
                "tier": ustatus.get("userTier", ""),
                "plan": ustatus.get("planStatus", {}).get("planInfo", {}).get("planName", "Standard"),
            }

            plan_info = ustatus.get("planStatus", {}).get("planInfo", {})
            avail_credits = ustatus.get("planStatus", {}).get("availablePromptCredits")
            monthly_credits = plan_info.get("monthlyPromptCredits")

            if avail_credits is not None and monthly_credits is not None:
                avail = float(avail_credits)
                monthly = float(monthly_credits)
                res["prompt_credits"] = {
                    "available": avail,
                    "monthly": monthly,
                    "used": max(0.0, monthly - avail),
                    "used_percentage": round(((monthly - avail) / monthly) * 100, 1) if monthly > 0 else 0,
                    "remaining_percentage": round((avail / monthly) * 100, 1) if monthly > 0 else 0,
                }

            # Parse client model configs
            configs = ustatus.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
            now = datetime.now(timezone.utc)
            models_list = []
            for m in configs:
                label = m.get("label", "Unknown")
                mid = m.get("modelOrAlias", {}).get("model") or m.get("model_or_alias", {}).get("model") or "unknown"
                qinfo = m.get("quotaInfo") or m.get("quota_info") or {}
                rem_fraction = qinfo.get("remainingFraction") if "remainingFraction" in qinfo else qinfo.get("remaining_fraction")
                reset_raw = qinfo.get("resetTime") or qinfo.get("reset_time")

                reset_formatted = "Unknown"
                if reset_raw:
                    try:
                        dt = datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
                        diff_sec = (dt - now).total_seconds()
                        reset_formatted = self._format_duration(diff_sec)
                    except Exception:
                        pass

                models_list.append({
                    "label": label,
                    "model_id": mid,
                    "remaining_fraction": rem_fraction,
                    "remaining_percentage": round(rem_fraction * 100, 1) if rem_fraction is not None else None,
                    "reset_time": reset_raw,
                    "time_until_reset": reset_formatted,
                    "is_exhausted": rem_fraction == 0 if rem_fraction is not None else False,
                })
            res["models"] = sorted(models_list, key=lambda x: x["label"])

        except Exception as e:
            logger.warning(f"Could not retrieve user status: {e}")
            res["is_connected"] = False

        # 2. Fetch Quota Summary (5h and weekly groups)
        try:
            raw_summary = self.get_quota_summary()
            groups = raw_summary.get("response", {}).get("groups", [])
            now = datetime.now(timezone.utc)
            parsed_groups = []
            for g in groups:
                g_name = g.get("displayName") or g.get("display_name") or "Group"
                g_desc = g.get("description", "")
                raw_buckets = g.get("buckets", [])
                parsed_buckets = []
                for b in raw_buckets:
                    bid = b.get("bucketId") or b.get("bucket_id") or "bucket"
                    bname = b.get("displayName") or b.get("display_name") or bid
                    bdesc = b.get("description", "")
                    window = b.get("window", "")
                    rem_fraction = b.get("remainingFraction") if "remainingFraction" in b else b.get("remaining_fraction")
                    reset_raw = b.get("resetTime") or b.get("reset_time")

                    reset_formatted = "Unknown"
                    if reset_raw:
                        try:
                            dt = datetime.fromisoformat(reset_raw.replace("Z", "+00:00"))
                            diff_sec = (dt - now).total_seconds()
                            reset_formatted = self._format_duration(diff_sec)
                        except Exception:
                            pass

                    parsed_buckets.append({
                        "bucket_id": bid,
                        "display_name": bname,
                        "description": bdesc,
                        "window": window,
                        "remaining_fraction": rem_fraction,
                        "remaining_percentage": round(rem_fraction * 100, 1) if rem_fraction is not None else None,
                        "reset_time": reset_raw,
                        "time_until_reset": reset_formatted,
                        "is_exhausted": rem_fraction == 0 if rem_fraction is not None else False,
                    })

                parsed_groups.append({
                    "display_name": g_name,
                    "description": g_desc,
                    "buckets": parsed_buckets,
                })
            res["quota_groups"] = parsed_groups
        except Exception as e:
            logger.debug(f"Could not retrieve quota summary: {e}")

        return res

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Formats seconds into human-readable duration like '3d 16h' or '45m'."""
        if seconds <= 0:
            return "Ready"
        mins = int(seconds // 60)
        hours = mins // 60
        days = hours // 24
        if days > 0:
            rem_hours = hours % 24
            return f"{days}d {rem_hours}h"
        if hours > 0:
            rem_mins = mins % 60
            return f"{hours}h {rem_mins}m"
        return f"{mins}m"
