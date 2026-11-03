"""Process and runtime detector for Antigravity IDE and Language Server.

Detects running Antigravity components, language server binary PIDs, command-line arguments
(including CSRF tokens), listening network ports, and verifies active HTTPS RPC endpoints.
"""

import json
import logging
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import List, Optional

logger = logging.getLogger("antigravity_observer.process_detector")


@dataclass
class AntigravityProcessInfo:
    """Detailed runtime metadata for Antigravity processes."""
    ide_pid: Optional[int] = None
    language_server_pid: Optional[int] = None
    csrf_token: Optional[str] = None
    extension_server_port: Optional[int] = None
    extension_server_csrf_token: Optional[str] = None
    workspace_id: Optional[str] = None
    cloud_code_endpoint: Optional[str] = None
    rpc_port: Optional[int] = None
    lsp_port: Optional[int] = None
    all_listening_ports: List[int] = field(default_factory=list)
    is_running: bool = False
    rpc_available: bool = False
    status_message: str = "Not detected"

    def to_dict(self):
        return asdict(self)


class ProcessDetector:
    """Discovers Antigravity IDE and Language Server runtime state."""

    def __init__(self):
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def detect(self) -> AntigravityProcessInfo:
        """Runs full detection cycle for Antigravity IDE and Language Server."""
        info = AntigravityProcessInfo()

        # 1. Detect IDE Main Process
        info.ide_pid = self._find_ide_pid()

        # 2. Detect Language Server Process
        ls_info = self._find_language_server_process()
        if ls_info:
            info.language_server_pid = ls_info["pid"]
            info.csrf_token = ls_info.get("csrf_token")
            info.extension_server_port = ls_info.get("extension_server_port")
            info.extension_server_csrf_token = ls_info.get("extension_server_csrf_token")
            info.workspace_id = ls_info.get("workspace_id")
            info.cloud_code_endpoint = ls_info.get("cloud_code_endpoint")
            info.is_running = True

            # 3. Find listening ports for Language Server PID
            ports = self._get_listening_ports(info.language_server_pid)
            info.all_listening_ports = ports

            # 4. Probe ports for HTTPS Connect RPC endpoint
            if info.csrf_token and ports:
                rpc_port = self._find_working_rpc_port(ports, info.csrf_token)
                if rpc_port:
                    info.rpc_port = rpc_port
                    info.rpc_available = True
                    info.status_message = f"Connected to Language Server (PID: {info.language_server_pid}, Port: {info.rpc_port})"
                else:
                    info.status_message = f"Language Server running (PID: {info.language_server_pid}), RPC port probe pending"
            else:
                info.status_message = f"Language Server running (PID: {info.language_server_pid}), CSRF token: {'found' if info.csrf_token else 'missing'}"
        else:
            if info.ide_pid:
                info.is_running = True
                info.status_message = f"Antigravity IDE running (PID: {info.ide_pid}), Language server not yet spawned"
            else:
                info.is_running = False
                info.status_message = "Antigravity IDE is not currently running"

        return info

    def _find_ide_pid(self) -> Optional[int]:
        """Finds Antigravity IDE Electron main process PID."""
        try:
            cmd = ["pgrep", "-f", "Antigravity IDE.app/Contents/MacOS/Electron"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                return int(lines[0].strip())
        except Exception as e:
            logger.debug(f"Error checking IDE PID: {e}")
        return None

    def _find_language_server_process(self) -> Optional[dict]:
        """Finds language_server_* process and parses its command-line args."""
        try:
            # Match language_server_macos_arm, language_server_macos, linux, etc.
            cmd = ["pgrep", "-fl", "language_server"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode != 0 or not res.stdout.strip():
                # Fallback to ps
                ps_res = subprocess.run(["ps", "-ax", "-o", "pid,command"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                lines = [l for l in ps_res.stdout.splitlines() if "language_server" in l and "grep" not in l]
            else:
                lines = res.stdout.strip().split("\n")

            for line in lines:
                if "language_server" not in line or "--csrf_token" not in line:
                    continue

                parts = line.strip().split(maxsplit=1)
                pid = int(parts[0])
                cmdline = parts[1] if len(parts) > 1 else ""

                # Extract arguments
                csrf_match = re.search(r"--csrf_token[=\s]+([a-zA-Z0-9\-]+)", cmdline)
                ext_port_match = re.search(r"--extension_server_port[=\s]+(\d+)", cmdline)
                ext_csrf_match = re.search(r"--extension_server_csrf_token[=\s]+([a-zA-Z0-9\-]+)", cmdline)
                ws_match = re.search(r"--workspace_id[=\s]+([^\s]+)", cmdline)
                endpoint_match = re.search(r"--cloud_code_endpoint[=\s]+([^\s]+)", cmdline)

                return {
                    "pid": pid,
                    "csrf_token": csrf_match.group(1) if csrf_match else None,
                    "extension_server_port": int(ext_port_match.group(1)) if ext_port_match else None,
                    "extension_server_csrf_token": ext_csrf_match.group(1) if ext_csrf_match else None,
                    "workspace_id": ws_match.group(1) if ws_match else None,
                    "cloud_code_endpoint": endpoint_match.group(1) if endpoint_match else None,
                }
        except Exception as e:
            logger.error(f"Error finding language server process: {e}")
        return None

    def _get_listening_ports(self, pid: int) -> List[int]:
        """Finds TCP listening ports belonging to a process PID using lsof."""
        ports = []
        try:
            cmd = ["lsof", "-nP", "-a", "-iTCP", "-sTCP:LISTEN", "-p", str(pid)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    m = re.search(r":(\d+)\s+\(LISTEN\)", line)
                    if m:
                        p = int(m.group(1))
                        if p not in ports:
                            ports.append(p)
        except Exception as e:
            logger.debug(f"Error querying ports for PID {pid}: {e}")
        return sorted(ports)

    def _find_working_rpc_port(self, ports: List[int], csrf_token: str) -> Optional[int]:
        """Tests ports to find the active HTTPS Connect RPC endpoint."""
        for port in ports:
            try:
                url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUnleashData"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "X-Codeium-Csrf-Token": csrf_token,
                        "Connect-Protocol-Version": "1",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=1.0) as res:
                    if res.status == 200:
                        return port
            except Exception:
                continue
        return None
