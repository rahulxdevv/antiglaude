"""CLI management interface for Antiglaude Bridge."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from gateway.auth.project_resolver import project_resolver
from gateway.auth.token_manager import token_manager
from gateway.config import DEFAULT_CONFIG


def cmd_status(args):
    """Check bridge health, OAuth token, and upstream model tier."""
    print("Checking Antiglaude Bridge status...")
    db_paths = token_manager.get_candidate_db_paths()
    print(f"Found {len(db_paths)} local Antigravity state database(s):")
    for p in db_paths:
        print(f"  - {p}")

    async def _check():
        try:
            token = await token_manager.get_access_token()
            print(f"OAuth Token: Active (len={len(token)})")
            proj, tier = await project_resolver.resolve(token)
            print(f"Project ID: {proj}")
            print(f"Account Tier: {tier}")
        except Exception as e:
            print(f"Auth / Resolver error: {e}")

    asyncio.run(_check())

    # Check if local gateway is running
    url = f"http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            data = json.loads(resp.read().decode())
            print(f"\nGateway Server: RUNNING on http://{DEFAULT_CONFIG.host}:{DEFAULT_CONFIG.port}")
            print(f"Health response: {data}")
    except Exception:
        print(f"\nGateway Server: NOT running on port {DEFAULT_CONFIG.port} (run `start` to launch)")


def cmd_start(args):
    """Start the gateway server."""
    import uvicorn
    from gateway.server import app

    host = args.host or DEFAULT_CONFIG.host
    port = args.port or DEFAULT_CONFIG.port
    print(f"Starting Antiglaude Bridge Gateway on http://{host}:{port}...")
    uvicorn.run(app, host=host, port=port, log_level="info")


def cmd_claude(args):
    """Run Claude Code CLI pointing directly to the bridge."""
    prompt = " ".join(args.prompt) if args.prompt else None
    gateway_url = f"http://{args.host}:{args.port}"

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = gateway_url
    env["ANTHROPIC_API_KEY"] = "bridge-token"
    env["ANTHROPIC_MODEL"] = args.model

    cmd = ["claude"]
    if args.permission_mode:
        cmd.extend(["--permission-mode", args.permission_mode])
    if prompt:
        cmd.extend(["-p", prompt])

    print(f"Running Claude Code via {gateway_url} (model: {args.model})...")
    subprocess.run(cmd, env=env)


def main():
    parser = argparse.ArgumentParser(description="Antiglaude Bridge CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # status
    subparsers.add_parser("status", help="Check bridge and token health")

    # start / serve
    for name in ("start", "serve"):
        p = subparsers.add_parser(name, help="Start the Anthropic & OpenAI compatible gateway server")
        p.add_argument("--host", default=DEFAULT_CONFIG.host, help="Host to bind")
        p.add_argument("--port", type=int, default=DEFAULT_CONFIG.port, help="Port to bind")

    # claude
    claude_p = subparsers.add_parser("claude", help="Run Claude Code through the bridge")
    claude_p.add_argument("--host", default=DEFAULT_CONFIG.host, help="Gateway host")
    claude_p.add_argument("--port", type=int, default=DEFAULT_CONFIG.port, help="Gateway port")
    claude_p.add_argument("--model", default="claude-sonnet-4-6", help="Model to use")
    claude_p.add_argument("--permission-mode", default="auto", help="Permission mode")
    claude_p.add_argument("prompt", nargs="*", help="Optional prompt to pass to claude -p")

    args = parser.parse_args()
    if args.command == "status":
        cmd_status(args)
    elif args.command in ("start", "serve"):
        cmd_start(args)
    elif args.command == "claude":
        cmd_claude(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
