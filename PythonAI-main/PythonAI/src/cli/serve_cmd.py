from __future__ import annotations

import argparse
import os
import sys

from src.cli.common import ROOT, project_python, run


def serve_cmd(args: argparse.Namespace) -> int:
    """Start the PythonAI FastAPI server via uvicorn."""
    port = args.port
    host = args.host

    print(f"[Serve] Starting PythonAI FastAPI server on {host}:{port}...\n")
    print("  Endpoints:")
    print("    POST /ask          Ask a Python question")
    print("    POST /chat         Chat with history")
    print("    GET  /health       Health check")
    print("    GET  /stats        Database statistics")
    print("    GET  /docs         Interactive API docs (Swagger UI)\n")

    try:
        import uvicorn
    except ImportError:
        print("[FAIL] uvicorn is not installed. Run: pip install uvicorn")
        return 1

    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        log_level="info",
    )
    return 0


def webui_run(args: argparse.Namespace) -> int:
    """Launch the Streamlit Web UI."""
    if args.daemon:
        import subprocess as sp

        print(f"[Daemon] Starting Web UI on port {args.port} in background...")
        creationflags = 0
        if sys.platform == "win32":
            creationflags = sp.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        else:
            # On Unix, fork and detach
            pid = os.fork()
            if pid > 0:
                print(f"[Daemon] PID: {pid}")
                print(f"[Daemon] Web UI starting at http://localhost:{args.port}")
                return 0
        cmd = [
            str(project_python()),
            "-m",
            "streamlit",
            "run",
            str(ROOT / "src" / "webui" / "app.py"),
            "--server.port",
            str(args.port),
            "--browser.gatherUsageStats",
            "false",
        ]
        sp.Popen(cmd, creationflags=creationflags, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        print(f"[Daemon] Web UI started at http://localhost:{args.port}")
        return 0

    return run(
        [
            str(project_python()),
            "-m",
            "streamlit",
            "run",
            str(ROOT / "src" / "webui" / "app.py"),
            "--server.port",
            str(args.port),
            "--browser.gatherUsageStats",
            "false",
        ]
    )


def dashboard_cmd(args: argparse.Namespace) -> int:
    """Open the live OMNISCIENT AI dashboard."""
    import subprocess as sp

    dashboard_path = ROOT / "dashboard.html"
    if not dashboard_path.exists():
        print(f"[Error] Dashboard not found at: {dashboard_path}")
        return 1
    print("[Dashboard] Opening live visualization...")
    sp.Popen(["cmd", "/c", "start", str(dashboard_path)], shell=True)
    return 0
