"""OAuth token discovery, extraction, and lifecycle management."""

import base64
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

from gateway.config import DEFAULT_CONFIG

logger = logging.getLogger("gateway.auth")


class TokenManager:
    """Manages Google OAuth tokens for Antigravity Cloud Code."""

    def __init__(self, config=DEFAULT_CONFIG):
        self.config = config
        self._cached_access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._refresh_token: Optional[str] = None
        self._account_email: Optional[str] = None
        self._project_id: Optional[str] = config.default_project_id

    def get_candidate_db_paths(self) -> List[Path]:
        """Locate Antigravity SQLite databases across platforms."""
        home = Path.home()
        candidates = [
            home / "Library/Application Support/Antigravity/User/globalStorage/state.vscdb",
            home / "Library/Application Support/Antigravity IDE/User/globalStorage/state.vscdb",
            home / ".config/Antigravity/User/globalStorage/state.vscdb",
            home / "AppData/Roaming/Antigravity/User/globalStorage/state.vscdb",
            home / ".gemini/antigravity-ide/User/globalStorage/state.vscdb",
        ]
        return [p for p in candidates if p.exists() and p.is_file()]

    def extract_refresh_token_from_db(self) -> Tuple[Optional[str], Optional[str]]:
        """Extract refresh token and email from Antigravity local state database."""
        db_paths = self.get_candidate_db_paths()
        if not db_paths:
            logger.warning("No Antigravity state.vscdb databases found.")
            return None, None

        for db_path in db_paths:
            try:
                # Open read-only using URI
                uri = f"file:{db_path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=3.0)
                cursor = conn.cursor()

                # 1. Try unified state sync oauthToken protobuf
                cursor.execute(
                    "SELECT value FROM ItemTable WHERE key = 'antigravityUnifiedStateSync.oauthToken'"
                )
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        raw = base64.b64decode(row[0])
                        match = re.search(rb'\{.*"accessToken".*\}', raw)
                        if match:
                            data = json.loads(match.group(0).decode("utf-8", errors="ignore"))
                            r_token = data.get("refreshToken")
                            if r_token:
                                logger.info("Successfully extracted refresh token from %s", db_path.name)
                                conn.close()
                                return r_token, None
                    except Exception as e:
                        logger.debug("Failed parsing protobuf in %s: %s", db_path, e)

                # 2. Try antigravityAuthStatus for email or token
                cursor.execute(
                    "SELECT value FROM ItemTable WHERE key = 'antigravityAuthStatus'"
                )
                auth_row = cursor.fetchone()
                if auth_row and auth_row[0]:
                    try:
                        auth_data = json.loads(auth_row[0])
                        email = auth_data.get("email")
                        if email:
                            self._account_email = email
                    except Exception:
                        pass

                conn.close()
            except Exception as e:
                logger.debug("Error reading %s: %s", db_path, e)

        return None, self._account_email

    async def refresh_access_token(self, refresh_token: str) -> str:
        """Call Google OAuth2 token endpoint to obtain a new access token."""
        data = {
            "client_id": self.config.oauth_client_id,
            "client_secret": self.config.oauth_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.config.oauth_token_url, data=data, headers=headers)
            if resp.status_code != 200:
                err_text = resp.text
                logger.error("Token refresh failed: %d - %s", resp.status_code, err_text[:200])
                raise RuntimeError(f"Token refresh failed: {resp.status_code} {err_text[:200]}")

            payload = resp.json()
            access_token = payload.get("access_token")
            expires_in = payload.get("expires_in", 3600)

            if not access_token:
                raise RuntimeError("OAuth response missing access_token")

            self._cached_access_token = access_token
            # Set expiration with a 5-minute safety margin
            self._token_expires_at = time.time() + expires_in - 300
            logger.info("Successfully refreshed access token (valid for %ds)", expires_in)
            return access_token

    async def get_access_token(self) -> str:
        """Get a valid access token, auto-refreshing if expired or nearing expiry."""
        now = time.time()
        if self._cached_access_token and now < self._token_expires_at:
            return self._cached_access_token

        # Check if we have a refresh token
        if not self._refresh_token:
            r_token, email = self.extract_refresh_token_from_db()
            if r_token:
                self._refresh_token = r_token
                if email:
                    self._account_email = email
            else:
                # Check environment variable
                env_refresh = os.environ.get("GOOGLE_REFRESH_TOKEN")
                if env_refresh:
                    self._refresh_token = env_refresh

        if not self._refresh_token:
            raise RuntimeError(
                "No Google refresh token found. Ensure Antigravity is logged in or provide GOOGLE_REFRESH_TOKEN."
            )

        return await self.refresh_access_token(self._refresh_token)

    @property
    def account_email(self) -> str:
        return self._account_email or "default@antigravity"

    @property
    def project_id(self) -> str:
        return self._project_id or self.config.default_project_id

    def set_project_id(self, project_id: str):
        self._project_id = project_id


# Global instance
token_manager = TokenManager()
