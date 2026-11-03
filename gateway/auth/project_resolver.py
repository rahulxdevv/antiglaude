"""Project ID and subscription tier resolver via loadCodeAssist API."""

import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from gateway.auth.token_manager import token_manager
from gateway.config import DEFAULT_CONFIG

logger = logging.getLogger("gateway.project_resolver")


class ProjectResolver:
    """Discovers project ID and account tier from Google Cloud Code."""

    def __init__(self, config=DEFAULT_CONFIG):
        self.config = config
        self._cached_project_id: Optional[str] = None
        self._cached_tier: Optional[str] = None

    async def resolve(self, access_token: str) -> Tuple[str, str]:
        """Query loadCodeAssist to get project ID and subscription tier."""
        if self._cached_project_id and self._cached_tier:
            return self._cached_project_id, self._cached_tier

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/hub/1.107.0 darwin/arm64",
            "X-Client-Name": "antigravity",
            "X-Client-Version": "1.107.0",
            "x-goog-api-client": "gl-node/18.18.2 fire/0.8.6 grpc/1.10.x",
        }

        body = {
            "metadata": {
                "ideType": 9,  # Antigravity IDE
                "platform": 2,  # Darwin ARM64
                "pluginType": 2,  # Gemini
            },
            "mode": 1,
        }

        endpoints = [
            f"{self.config.cloudcode_endpoints[1]}/v1internal:loadCodeAssist",
            f"{self.config.cloudcode_endpoints[0]}/v1internal:loadCodeAssist",
        ]

        project_id = self.config.default_project_id
        tier = "free"

        async with httpx.AsyncClient(timeout=10.0) as client:
            for url in endpoints:
                try:
                    resp = await client.post(url, json=body, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_proj = data.get("cloudaicompanionProject")
                        if isinstance(raw_proj, str) and raw_proj:
                            project_id = raw_proj
                        elif isinstance(raw_proj, dict) and raw_proj.get("id"):
                            project_id = raw_proj["id"]

                        paid_tier = data.get("paidTier", {})
                        current_tier = data.get("currentTier", {})
                        tier_id = paid_tier.get("id") or current_tier.get("id", "free-tier")
                        tier = tier_id
                        logger.info("Discovered Project: %s, Tier: %s", project_id, tier)
                        break
                    else:
                        logger.debug("loadCodeAssist at %s returned status %d", url, resp.status_code)
                except Exception as e:
                    logger.debug("loadCodeAssist error at %s: %s", url, e)

        self._cached_project_id = project_id
        self._cached_tier = tier
        token_manager.set_project_id(project_id)
        return project_id, tier


project_resolver = ProjectResolver()
