"""Gateway configuration and constants."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class GatewayConfig:
    # Server host & port
    host: str = "127.0.0.1"
    port: int = 8080

    # Upstream Endpoints
    cloudcode_endpoints: List[str] = field(
        default_factory=lambda: [
            "https://daily-cloudcode-pa.googleapis.com",
            "https://cloudcode-pa.googleapis.com",
        ]
    )

    # OAuth Client credentials (dynamically loaded from env or local untracked credentials file)
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_token_url: str = "https://oauth2.googleapis.com/token"


    # Default Project ID fallback
    default_project_id: str = "aicode-consumers"

    # Direct Gemini API Key (optional fallback/alternative provider)
    gemini_api_key: Optional[str] = None

    # Model Mappings: Map requested Anthropic / Claude models to canonical backend models
    model_aliases: Dict[str, str] = field(
        default_factory=lambda: {
            # Claude mappings
            "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
            "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
            "claude-3-5-sonnet": "claude-sonnet-4-6",
            "claude-3-opus-20240229": "claude-opus-4-6-thinking",
            "claude-3-haiku-20240307": "gemini-3-flash",
            "claude-sonnet-4-5": "claude-sonnet-4-6",
            "claude-sonnet-4-5-thinking": "claude-sonnet-4-6",
            "claude-opus-4-5-thinking": "claude-opus-4-6-thinking",
            # Native model passthroughs
            "claude-sonnet-4-6": "claude-sonnet-4-6",
            "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
            "gemini-3-flash": "gemini-3-flash",
            "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
            "gemini-2.5-pro": "gemini-2.5-pro",
            "gemini-2.5-flash": "gemini-2.5-flash",
        }
    )

    # Default model if requested model is not found
    default_model: str = "claude-sonnet-4-6"

    # Telemetry & Observer integration
    observer_port: int = 51676
    enable_observer_telemetry: bool = True

    # Identity scrubber rules
    scrub_rules: List[tuple] = field(
        default_factory=lambda: [
            (r"\bNous Research\b", "the assistant team"),
            (r"\bHermes Agent\b", "the assistant"),
            (r"\bHermes\b", "the assistant"),
            (r"\bClaude Code\b", "the assistant"),
            (r"\bAnthropic\b", "the vendor"),
        ]
    )


def load_config() -> GatewayConfig:
    """Load configuration from environment variables and local credentials file."""
    import json
    cfg = GatewayConfig()
    cfg.host = os.environ.get("GATEWAY_HOST", cfg.host)
    cfg.port = int(os.environ.get("GATEWAY_PORT", str(cfg.port)))
    cfg.default_model = os.environ.get("GATEWAY_DEFAULT_MODEL", cfg.default_model)
    cfg.gemini_api_key = os.environ.get("GEMINI_API_KEY", None)

    # Dynamic OAuth credentials
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    cred_paths = [
        Path(__file__).parent / "auth" / "credentials.local.json",
        Path.home() / ".config" / "antigravity" / "credentials.json",
        Path.cwd() / "credentials.json",
    ]
    for cp in cred_paths:
        if cp.exists() and cp.is_file():
            try:
                with open(cp, "r") as f:
                    cdata = json.load(f)
                    client_id = client_id or cdata.get("client_id")
                    client_secret = client_secret or cdata.get("client_secret")
            except Exception:
                pass
            if client_id and client_secret:
                break

    if client_id:
        cfg.oauth_client_id = client_id
    if client_secret:
        cfg.oauth_client_secret = client_secret

    return cfg


DEFAULT_CONFIG = load_config()

