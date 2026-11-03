"""macOS LaunchAgent daemon management for Antiglaude Bridge."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Optional

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_NAME = "com.antiglaude.bridge.plist"
PLIST_PATH = LAUNCH_AGENTS_DIR / PLIST_NAME
LOG_DIR = Path.home() / ".antiglaude"
STDOUT_LOG = LOG_DIR / "bridge.stdout.log"
STDERR_LOG = LOG_DIR / "bridge.stderr.log"


def get_plist_content(repo_dir: Optional[str] = None, port: int = 8080) -> dict:
    """Generate the launchd plist configuration dictionary."""
    if not repo_dir:
        repo_dir = str(Path(__file__).resolve().parent.parent.parent)

    # Use virtualenv python if present, else sys.executable
    venv_py = Path(repo_dir) / ".venv" / "bin" / "python"
    python_bin = str(venv_py) if venv_py.exists() else sys.executable

    return {
        "Label": "com.antiglaude.bridge",
        "ProgramArguments": [
            python_bin,
            "-m",
            "gateway.cli",
            "start",
            "--port",
            str(port),
        ],
        "WorkingDirectory": repo_dir,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(STDOUT_LOG),
        "StandardErrorPath": str(STDERR_LOG),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
            "HOME": str(Path.home()),
        },
    }


def install_launchagent(repo_dir: Optional[str] = None, port: int = 8080) -> bool:
    """Install and activate the macOS LaunchAgent."""
    try:
        LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        plist_data = get_plist_content(repo_dir=repo_dir, port=port)

        # Write binary or XML plist
        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist_data, f)

        # Unload any existing instance first
        subprocess.run(
            ["launchctl", "unload", str(PLIST_PATH)],
            capture_output=True,
            text=True,
        )

        # Load and start daemon
        res = subprocess.run(
            ["launchctl", "load", "-w", str(PLIST_PATH)],
            capture_output=True,
            text=True,
        )

        if res.returncode == 0:
            print(f"Installed LaunchAgent to {PLIST_PATH}")
            print(f"Bridge daemon started. Output logs at {STDOUT_LOG}")
            return True
        else:
            print(f"Warning: launchctl load returned code {res.returncode}: {res.stderr}")
            return False

    except Exception as e:
        print(f"Failed installing LaunchAgent: {e}")
        return False


def uninstall_launchagent() -> bool:
    """Stop and remove the macOS LaunchAgent."""
    try:
        if PLIST_PATH.exists():
            subprocess.run(
                ["launchctl", "unload", "-w", str(PLIST_PATH)],
                capture_output=True,
                text=True,
            )
            PLIST_PATH.unlink()
            print("Removed LaunchAgent plist and stopped background service.")
            return True
        else:
            print("LaunchAgent plist does not exist.")
            return True
    except Exception as e:
        print(f"Failed uninstalling LaunchAgent: {e}")
        return False


def status_launchagent() -> None:
    """Check the running status of the daemon."""
    print("Checking macOS LaunchAgent status...")
    if not PLIST_PATH.exists():
        print(f"LaunchAgent is NOT installed (no file at {PLIST_PATH})")
        return

    res = subprocess.run(
        ["launchctl", "list", "com.antiglaude.bridge"],
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        print("Daemon Status: RUNNING via launchd")
        print(res.stdout)
    else:
        print("Daemon Status: Loaded in launchd but not actively running or failed:")
        print(res.stderr or res.stdout)

    if STDOUT_LOG.exists():
        print(f"\nLast 5 lines of stdout ({STDOUT_LOG}):")
        lines = STDOUT_LOG.read_text().strip().splitlines()[-5:]
        for line in lines:
            print(f"  {line}")
