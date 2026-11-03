"""Diagnostic record export engine.

Exports Antigravity observable interactions, metrics, and execution timelines
into structured JSON archives, comprehensive Markdown reports, and HAR format.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class DiagnosticExporter:
    """Generates structured diagnostic export records."""

    @staticmethod
    def export_json(
        runtime_info: Dict[str, Any],
        quota_status: Dict[str, Any],
        conversation_meta: Dict[str, Any],
        timeline: List[Dict[str, Any]],
        requests: List[Dict[str, Any]],
        analytics: Dict[str, Any],
    ) -> str:
        """Exports complete diagnostic record as formatted JSON."""
        data = {
            "antigravity_observer_export": {
                "version": "1.0.0",
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
            "runtime_environment": runtime_info,
            "quota_and_account": quota_status,
            "conversation": conversation_meta,
            "execution_timeline": timeline,
            "recent_requests": requests,
            "analytics_summary": analytics,
        }
        return json.dumps(data, indent=2)

    @staticmethod
    def export_markdown_report(
        runtime_info: Dict[str, Any],
        quota_status: Dict[str, Any],
        conversation_meta: Dict[str, Any],
        timeline: List[Dict[str, Any]],
        analytics: Dict[str, Any],
    ) -> str:
        """Exports executive developer diagnostic report in Markdown format."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        conv_id = conversation_meta.get("conversation_id", "Unknown")
        user = quota_status.get("user", {})
        credits = quota_status.get("prompt_credits") or {}

        md = []
        md.append(f"# Antigravity Developer Observability Diagnostic Report")
        md.append(f"**Generated:** {now_str} | **Conversation ID:** `{conv_id}`\n")

        md.append("## 1. Runtime & Environment Status")
        md.append(f"- **Language Server Status:** {runtime_info.get('status_message', 'Active')}")
        md.append(f"- **Language Server PID:** `{runtime_info.get('language_server_pid', 'N/A')}`")
        md.append(f"- **RPC Port:** `{runtime_info.get('rpc_port', 'N/A')}`")
        md.append(f"- **Workspace ID:** `{runtime_info.get('workspace_id', 'N/A')}`")
        md.append(f"- **Cloud Code Endpoint:** `{runtime_info.get('cloud_code_endpoint', 'https://daily-cloudcode-pa.googleapis.com')}`\n")

        md.append("## 2. Model & Quota Health")
        md.append(f"- **Active User:** {user.get('name', 'Developer')} ({user.get('email', 'N/A')}) | Plan: `{user.get('plan', 'Pro')}`")
        if credits:
            md.append(f"- **Prompt Credits:** {credits.get('available', 0):,g} / {credits.get('monthly', 0):,g} ({credits.get('remaining_percentage', 0)}% remaining)")
        md.append("")

        # Quota Buckets Table
        groups = quota_status.get("quota_groups", [])
        if groups:
            md.append("### Quota Buckets")
            md.append("| Group | Window | Remaining | Reset Countdown |")
            md.append("|:---|:---|:---|:---|")
            for g in groups:
                gname = g.get("display_name", "")
                for b in g.get("buckets", []):
                    w = b.get("window", "")
                    rem = f"{b.get('remaining_percentage', 0):.1f}%"
                    rst = b.get("time_until_reset", "Ready")
                    md.append(f"| {gname} | {w} | {rem} | {rst} |")
            md.append("")

        # Analytics Table
        md.append("## 3. Conversation & Token Analytics")
        md.append(f"- **Total Steps Recorded:** {conversation_meta.get('total_steps', 0)}")
        md.append(f"- **Planner Turns (LLM Generations):** {conversation_meta.get('planner_responses', 0)}")
        md.append(f"- **Total Tool Invocations:** {conversation_meta.get('tool_calls_total', 0)}")
        md.append(f"- **Peak Prompt Context Size:** {conversation_meta.get('prompt_tokens_peak', 0):,} tokens")
        md.append(f"- **Cumulative Output Tokens:** {conversation_meta.get('cumulative_output_tokens', 0):,} tokens")
        md.append(f"- **Cumulative Reasoning/Thinking Tokens:** {conversation_meta.get('cumulative_thinking_tokens', 0):,} tokens\n")

        # Tool Breakdown
        breakdown = conversation_meta.get("tool_breakdown", {})
        if breakdown:
            md.append("### Tool Invocations Breakdown")
            md.append("| Tool Name | Invocations |")
            md.append("|:---|:---|")
            for tname, cnt in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
                md.append(f"| `{tname}` | {cnt} |")
            md.append("")

        # Execution Timeline Summary
        md.append("## 4. Execution Lifecycle & Agent Turns")
        turn_num = 1
        for cycle in timeline:
            ctype = cycle.get("cycle_type")
            if ctype == "user_input":
                prompt_snippet = cycle.get("prompt", "")[:200].replace("\n", " ")
                md.append(f"### User Input (Step {cycle.get('step_index')})")
                md.append(f"> {prompt_snippet}...\n")
            elif ctype == "agent_turn":
                mname = cycle.get("model", "Gemini 3.8 Flash (High)")
                toks = cycle.get("tokens", {})
                tools = [t.get("name") for t in cycle.get("tool_calls_planned", [])]
                tool_str = ", ".join([f"`{t}`" for t in tools]) if tools else "None"
                md.append(f"#### Turn {turn_num}: {mname}")
                md.append(f"- **Tokens:** Prompt: `{toks.get('prompt', 0):,}` | Output: `{toks.get('output', 0):,}` | Reasoning: `{toks.get('thinking', 0):,}`")
                md.append(f"- **Tools Planned:** {tool_str}")
                if cycle.get("thinking"):
                    thinking_snip = cycle.get("thinking", "")[:250].replace("\n", " ")
                    md.append(f"- **Reasoning Excerpt:** *\"{thinking_snip}...\"*")
                md.append("")
                turn_num += 1

        md.append("---")
        md.append("*Generated by Antigravity Observer - Engineering Observability Platform*")
        return "\n".join(md)
