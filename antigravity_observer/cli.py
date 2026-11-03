"""Command Line Interface (CLI) for Antigravity Observer.

Supports:
  - serve: Start the web dashboard and background collector
  - status: Inspect running Antigravity IDE, language server, and quota status
  - analyze: Print detailed token and execution analysis for a conversation
  - export: Export diagnostic data as JSON or Markdown
"""

import argparse
import json
import os
import sys
import webbrowser

import uvicorn

from antigravity_observer.collector.correlator import EventCorrelator
from antigravity_observer.collector.process_detector import ProcessDetector
from antigravity_observer.collector.rpc_client import LanguageServerRpcClient
from antigravity_observer.collector.sqlite_reader import SqliteReader
from antigravity_observer.collector.transcript_parser import TranscriptParser
from antigravity_observer.server.export import DiagnosticExporter
from antigravity_observer.storage.observer_db import ObserverDatabase


def cmd_status(args):
    """Prints current Antigravity runtime, language server, and quota status."""
    print("=" * 60)
    print("      ANTIGRAVITY DEVELOPER OBSERVABILITY PLATFORM")
    print("=" * 60)

    detector = ProcessDetector()
    info = detector.detect()

    print(f"\n[1] Runtime Detection:")
    print(f"  • IDE Running:            {'YES' if info.is_running else 'NO'}")
    if info.ide_pid:
        print(f"  • IDE Main PID:           {info.ide_pid}")
    if info.language_server_pid:
        print(f"  • Language Server PID:    {info.language_server_pid}")
        print(f"  • CSRF Token:             {info.csrf_token[:8]}..." if info.csrf_token else "  • CSRF Token: None")
        print(f"  • Extension Callback:     Port {info.extension_server_port}")
        print(f"  • Listening Ports:        {info.all_listening_ports}")
        print(f"  • Active RPC Port:        {info.rpc_port or 'Not detected'}")
        print(f"  • Status:                 {info.status_message}")

    # Check RPC Quota & Account
    if info.rpc_port and info.csrf_token:
        print(f"\n[2] Live Quota & Account (via HTTPS Connect RPC):")
        try:
            client = LanguageServerRpcClient(info.rpc_port, info.csrf_token)
            status = client.get_comprehensive_status()
            user = status.get("user", {})
            print(f"  • User Name:              {user.get('name', 'N/A')}")
            print(f"  • User Email:             {user.get('email', 'N/A')}")
            print(f"  • Plan:                   {user.get('plan', 'N/A')} ({user.get('tier', 'N/A')})")

            credits = status.get("prompt_credits")
            if credits:
                print(f"  • Prompt Credits:         {credits['available']:,g} / {credits['monthly']:,g} ({credits['remaining_percentage']}% remaining)")

            groups = status.get("quota_groups", [])
            for g in groups:
                print(f"  • {g.get('display_name')}:")
                for b in g.get("buckets", []):
                    rem = f"{b.get('remaining_percentage', 0):.1f}%"
                    rst = b.get("time_until_reset", "Ready")
                    print(f"      - {b.get('display_name')}: {rem} remaining (Reset: {rst})")
        except Exception as e:
            print(f"  • Could not query RPC: {e}")

    # Check active conversation
    tp = TranscriptParser()
    active_cid = tp.get_active_conversation_id()
    if active_cid:
        sr = SqliteReader()
        tokens = sr.get_aggregate_tokens(active_cid)
        metrics = tp.get_conversation_metrics(active_cid)
        print(f"\n[3] Active Conversation:")
        print(f"  • ID:                     {active_cid}")
        print(f"  • Total Steps:            {metrics.get('total_steps', 0)}")
        print(f"  • Planner Turns:          {metrics.get('planner_responses', 0)}")
        print(f"  • Tool Invocations:       {metrics.get('tool_calls_total', 0)}")
        print(f"  • Peak Prompt Context:    {tokens.get('prompt_tokens_peak', 0):,} tokens")
        print(f"  • Cumulative Output:      {tokens.get('cumulative_output_tokens', 0):,} tokens")
        print(f"  • Cumulative Reasoning:   {tokens.get('cumulative_thinking_tokens', 0):,} tokens")
        print(f"  • Primary Model:          {tokens.get('primary_model', 'N/A')}")

    print("\n" + "=" * 60)


def cmd_analyze(args):
    """Analyzes a specific conversation or the active one."""
    tp = TranscriptParser()
    cid = args.conversation_id or tp.get_active_conversation_id()
    if not cid:
        print("No active conversation found to analyze.")
        sys.exit(1)

    sr = SqliteReader()
    metrics = tp.get_conversation_metrics(cid)
    tokens = sr.get_aggregate_tokens(cid)
    correlator = EventCorrelator(transcript_parser=tp, sqlite_reader=sr)
    timeline = correlator.get_unified_timeline(cid)

    print(f"\nExecution Analysis for Conversation: {cid}")
    print("=" * 70)
    print(f"Steps: {metrics.get('total_steps', 0)} | Planner Turns: {metrics.get('planner_responses', 0)} | Errors: {metrics.get('error_count', 0)}")
    print(f"Peak Prompt Tokens: {tokens.get('prompt_tokens_peak', 0):,} | Output Tokens: {tokens.get('cumulative_output_tokens', 0):,} | Reasoning Tokens: {tokens.get('cumulative_thinking_tokens', 0):,}")
    print(f"Duration: {metrics.get('duration_seconds', 0):.1f}s | Model: {tokens.get('primary_model', 'N/A')}")

    print("\nTool Usage Breakdown:")
    for tool, count in sorted(metrics.get("tool_breakdown", {}).items(), key=lambda x: x[1], reverse=True):
        print(f"  • {tool:25}: {count:4d} calls")

    print("\nRecent Agent Turns (last 5):")
    agent_turns = [c for c in timeline if c.get("cycle_type") == "agent_turn"]
    for turn in agent_turns[-5:]:
        sidx = turn.get("step_index")
        mname = turn.get("model")
        toks = turn.get("tokens", {})
        tools = [t.get("name") for t in turn.get("tool_calls_planned", [])]
        print(f"  [Step {sidx:3d}] {mname:25} | In: {toks.get('prompt', 0):6,d} | Out: {toks.get('output', 0):4,d} | Think: {toks.get('thinking', 0):4,d} | Tools: {tools}")


def cmd_export(args):
    """Exports diagnostic records to a file."""
    tp = TranscriptParser()
    cid = args.conversation_id or tp.get_active_conversation_id()
    if not cid:
        print("No conversation found to export.")
        sys.exit(1)

    detector = ProcessDetector()
    runtime = detector.detect().to_dict()
    client = LanguageServerRpcClient(runtime["rpc_port"], runtime["csrf_token"]) if runtime.get("rpc_port") and runtime.get("csrf_token") else None
    quota = client.get_comprehensive_status() if client else {}

    sr = SqliteReader()
    conv_meta = tp.get_conversation_metrics(cid)
    conv_meta.update(sr.get_aggregate_tokens(cid))

    correlator = EventCorrelator(transcript_parser=tp, sqlite_reader=sr)
    timeline = correlator.get_unified_timeline(cid)
    requests = correlator.get_requests_overview(limit=200)

    storage = ObserverDatabase()
    analytics = storage.get_analytics_summary()

    if args.format == "markdown":
        output = DiagnosticExporter.export_markdown_report(runtime, quota, conv_meta, timeline, analytics)
        default_file = f"antigravity_report_{cid[:8]}.md"
    else:
        output = DiagnosticExporter.export_json(runtime, quota, conv_meta, timeline, requests, analytics)
        default_file = f"antigravity_diagnostic_{cid[:8]}.json"

    target_file = args.output or default_file
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"Diagnostic record successfully exported to: {target_file}")


def cmd_serve(args):
    """Starts the standalone Antigravity Observer web dashboard and background collector."""
    print("=" * 60)
    print("      LAUNCHING ANTIGRAVITY OBSERVER DASHBOARD")
    print(f"      Host: http://{args.host}:{args.port}")
    print("=" * 60)

    if args.open_browser:
        def open_tab():
            import time
            time.sleep(1.0)
            webbrowser.open(f"http://{args.host}:{args.port}")
        import threading
        threading.Thread(target=open_tab, daemon=True).start()

    uvicorn.run("antigravity_observer.server.app:app", host=args.host, port=args.port, log_level="info")


def main():
    parser = argparse.ArgumentParser(description="Antigravity Developer Observability Platform")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Launch web dashboard and collector")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Binding host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=4949, help="Binding port (default: 4949)")
    serve_parser.add_argument("--open-browser", action="store_true", help="Automatically open dashboard in browser")

    # Status command
    subparsers.add_parser("status", help="Print runtime, process, and quota status")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze conversation token and tool metrics")
    analyze_parser.add_argument("--conversation-id", "-c", help="Conversation ID (defaults to active)")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export diagnostic bundle or markdown report")
    export_parser.add_argument("--conversation-id", "-c", help="Conversation ID (defaults to active)")
    export_parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Export format")
    export_parser.add_argument("--output", "-o", help="Target output filepath")

    args = parser.parse_args()
    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        # Default action is serve with open browser
        args.host = "127.0.0.1"
        args.port = 4949
        args.open_browser = True
        cmd_serve(args)


if __name__ == "__main__":
    main()
