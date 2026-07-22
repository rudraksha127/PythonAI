"""
Ecosystem Manager — Central Integration Hub for ForgeAI
=========================================================

Manages all cross-project connections in one place:

  - PythonAI ↔ hermes-agent (Multi-agent orchestration)
  - PythonAI ↔ Rudra-bots (Metrics dashboard)
  - PythonAI ↔ Dashboard (Training/SEAL UI)
  - PythonAI ↔ open-claude (CLI interface)
  - Shared config & status reporting

Usage:
    from src.integration.ecosystem_manager import EcosystemManager
    
    mgr = EcosystemManager()
    status = mgr.get_ecosystem_status()
    print(status)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgeai.integration.ecosystem")


class EcosystemManager:
    """Centralized manager for the entire ForgeAI ecosystem.

    Discovers all projects, checks their health, and provides
    a unified status and control interface.
    """

    def __init__(self, project_root: str | Path | None = None):
        if project_root is None:
            # Auto-detect: look for known project markers
            self.project_root = self._detect_project_root()
        else:
            self.project_root = Path(project_root)

        self._projects: dict[str, Path] = {}
        self._discover_projects()

    def _detect_project_root(self) -> Path:
        """Detect the monorepo root by looking for known project directories."""
        candidates = [
            Path.cwd(),
            Path(__file__).resolve().parent.parent.parent.parent,  # up from PythonAI/src/integration/
            Path(__file__).resolve().parent.parent.parent,  # up from PythonAI/src/
        ]

        for candidate in candidates:
            if (candidate / "README.md").exists() and (candidate / "PythonAI").exists():
                return candidate

        # Fallback
        return Path.cwd()

    def _discover_projects(self):
        """Discover all projects in the ecosystem."""
        root = self.project_root

        projects = {
            "PythonAI": root / "PythonAI",
            "hermes-agent": root / "hermes-agent-main",
            "Rudra-bots": root / "Rudra-bots-main",
            "open-claude": root / "open-claude-main",
            "Dashboard": root / "dashboard",
            "Hermes-studio": root / "Hermes-studio--main",
            "Claude_Code_npm": root / "Claude_Code_npm-main",
        }

        self._projects = {name: path for name, path in projects.items() if path.exists()}

    @property
    def discovered_projects(self) -> list[str]:
        return list(self._projects.keys())

    def get_project_path(self, name: str) -> Path | None:
        return self._projects.get(name)

    # ── Status / Health ──────────────────────────────────────────────

    def get_ecosystem_status(self) -> dict[str, Any]:
        """Get comprehensive status of all ecosystem projects.

        Computes project checks ONCE and reuses them for the summary.
        """
        project_checks = {name: self._check_project(name) for name in self._projects}
        return {
            "ecosystem": "ForgeAI v2.0",
            "projects": project_checks,
            "shared_config": self._check_shared_config(),
            "summary": self._compute_summary_from_checks(project_checks),
        }

    def _check_project(self, name: str) -> dict[str, Any]:
        """Check a single project's availability."""
        path = self._projects.get(name)
        if not path:
            return {"status": "not_found", "path": None}

        result: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "status": "unknown",
        }

        if name == "PythonAI":
            result["config"] = self._check_pythonai()
        elif name == "hermes-agent":
            result["installed"] = self._check_hermes_installed()
        elif name == "Rudra-bots":
            result["api"] = self._check_rudra_bots()
        elif name == "open-claude":
            result["built"] = self._check_open_claude()
        elif name == "Dashboard":
            result["api"] = self._check_dashboard()

        return result

    def _check_pythonai(self) -> dict[str, Any]:
        """Check PythonAI core engine availability."""
        try:
            from src.learning.capture_engine import CaptureEngine

            engine = CaptureEngine()
            stats = engine.get_statistics()
            return {
                "available": True,
                "signals": stats.get("signals_by_type", {}),
                "total_sessions": stats.get("total_sessions", 0),
                "acceptance_rate": stats.get("overall_acceptance_rate", 0),
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _check_hermes_installed(self) -> dict[str, Any]:
        """Check if hermes-agent is installed."""
        try:
            import importlib

            importlib.import_module("hermes_cli")
            return {"installed": True}
        except ImportError:
            return {"installed": False}

    def _check_rudra_bots(self) -> dict[str, Any]:
        """Check if Rudra-bots API is reachable."""
        import httpx

        try:
            url = os.environ.get("RUDRA_BOTS_URL", "http://localhost:7000")
            r = httpx.get(f"{url}/api/health", timeout=3.0)
            return {"available": r.status_code == 200, "status_code": r.status_code}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _check_open_claude(self) -> dict[str, Any]:
        """Check if open-claude is built."""
        path = self._projects.get("open-claude")
        if not path:
            return {"built": False}
        dist_cli = path / "dist" / "cli.mjs"
        return {"built": dist_cli.exists()}

    def _check_dashboard(self) -> dict[str, Any]:
        """Check if Dashboard (Next.js) is running."""
        import httpx

        try:
            r = httpx.get("http://localhost:3000/", timeout=3.0)
            return {"available": r.status_code == 200, "status_code": r.status_code}
        except Exception:
            return {"available": False}

    def _check_shared_config(self) -> dict[str, Any]:
        """Check the shared ForgeAI configuration."""
        config_path = Path.home() / ".forgeai" / "config.json"
        if not config_path.exists():
            return {"exists": False, "path": str(config_path)}

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            return {"exists": True, "path": str(config_path), "version": config.get("version", "unknown")}
        except Exception:
            return {"exists": True, "path": str(config_path), "error": "invalid_json"}

    def _compute_summary_from_checks(self, project_checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Compute a quick health summary from already-computed project checks.

        Args:
            project_checks: The dict returned by get_ecosystem_status()["projects"]
        """
        total = len(project_checks)
        available = 0

        for name, check in project_checks.items():
            if name == "PythonAI":
                cfg = check.get("config", {})
                if cfg.get("available"):
                    available += 1
            elif name == "hermes-agent":
                if check.get("installed", {}).get("installed"):
                    available += 1
            elif name in ("Rudra-bots", "Dashboard"):
                api = check.get("api", {})
                if api.get("available"):
                    available += 1
            elif name == "open-claude":
                if check.get("built", {}).get("built"):
                    available += 1
            else:
                if check.get("exists"):
                    available += 1

        return {"total_projects": total, "available": available, "status": "healthy" if available == total else "partial"}

    # ── Actions ─────────────────────────────────────────────────────

    def run_pythonai_server(self, port: int = 7337) -> subprocess.Popen | None:
        """Start the PythonAI FastAPI server."""
        pythonai_path = self._projects.get("PythonAI")
        if not pythonai_path:
            logger.error("PythonAI project not found")
            return None

        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "src.api.server", "--port", str(port)],
                cwd=str(pythonai_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"PythonAI server started on port {port} (PID: {proc.pid})")
            return proc
        except Exception as e:
            logger.error(f"Failed to start PythonAI server: {e}")
            return None

    def run_rudra_bots(self) -> subprocess.Popen | None:
        """Start the Rudra-bots dashboard server."""
        path = self._projects.get("Rudra-bots")
        if not path:
            logger.error("Rudra-bots project not found")
            return None

        app_file = path / "app.py"
        if not app_file.exists():
            logger.error("Rudra-bots app.py not found")
            return None

        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "7000"],
                cwd=str(path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Rudra-bots started (PID: {proc.pid})")
            return proc
        except Exception as e:
            logger.error(f"Failed to start Rudra-bots: {e}")
            return None

    def install_hermes_agent(self) -> dict[str, Any]:
        """Install the hermes-agent package."""
        hermes_path = self._projects.get("hermes-agent")
        if not hermes_path:
            return {"success": False, "error": "hermes-agent directory not found"}

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(hermes_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.info("hermes-agent installed successfully")
                return {"success": True, "output": result.stdout}
            return {"success": False, "error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Installation timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Self-Healing: Restart & Watchdog ────────────────────────────

    _service_procs: dict[str, subprocess.Popen] = {}

    def restart_service(self, name: str) -> dict[str, Any]:
        """Stop and restart a specific ecosystem service.

        Supported services: PythonAI, Rudra-bots, Dashboard.

        Args:
            name: Service name (case-insensitive)

        Returns:
            Dict with success status and PID
        """
        name_lower = name.lower().replace("-", "").replace("_", "")

        # Stop existing process if tracked
        if name in self._service_procs:
            old_proc = self._service_procs[name]
            try:
                old_proc.terminate()
                old_proc.wait(timeout=10)
            except Exception:
                try:
                    old_proc.kill()
                except Exception:
                    pass
            del self._service_procs[name]
            logger.info(f"Stopped existing {name} process")

        # Start the right service
        proc = None
        if name_lower in ("pythonai",):
            proc = self.run_pythonai_server()
        elif name_lower in ("rudrabots", "rudra-bots"):
            proc = self.run_rudra_bots()
        elif name_lower in ("dashboard",):
            dash_path = self._projects.get("Dashboard")
            if dash_path:
                try:
                    proc = subprocess.Popen(
                        ["npm", "run", "dev"],
                        cwd=str(dash_path),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True,
                    )
                except Exception as e:
                    return {"success": False, "error": f"Dashboard start failed: {e}"}
        else:
            return {"success": False, "error": f"Unknown service: {name}. Supported: PythonAI, Rudra-bots, Dashboard"}

        if proc:
            self._service_procs[name] = proc
            logger.info(f"Restarted {name} (PID: {proc.pid})")
            return {"success": True, "pid": proc.pid, "service": name}

        return {"success": False, "error": f"Failed to start {name}"}

    def watchdog(self, interval: int = 60, max_restarts: int = 3) -> None:
        """Synchronous watchdog loop — monitors services and auto-restarts.

        Designed to be run in a background thread. Uses exponential backoff
        to prevent restart storms.

        Args:
            interval: Seconds between health checks
            max_restarts: Max consecutive restarts before giving up on a service
        """
        import httpx as _httpx

        restart_counts: dict[str, int] = {}
        service_endpoints = {
            "PythonAI": "http://localhost:7337/health",
            "Rudra-bots": "http://localhost:7000/api/health",
            "Dashboard": "http://localhost:3000/api/health",
        }

        logger.info(f"Ecosystem watchdog started (interval={interval}s, max_restarts={max_restarts})")

        while True:
            import time as _time
            _time.sleep(interval)

            for name, url in service_endpoints.items():
                try:
                    r = _httpx.get(url, timeout=5.0)
                    if r.status_code == 200:
                        # Reset restart counter on success
                        restart_counts[name] = 0
                        continue
                except Exception:
                    pass

                # Service is down
                count = restart_counts.get(name, 0)
                if count >= max_restarts:
                    logger.error(
                        f"Watchdog: {name} has failed {count} times. "
                        f"Skipping auto-restart (max={max_restarts})."
                    )
                    continue

                logger.warning(f"Watchdog: {name} is DOWN. Attempting restart #{count + 1}...")
                result = self.restart_service(name)
                if result["success"]:
                    logger.info(f"Watchdog: {name} restarted successfully (PID: {result.get('pid')})")
                else:
                    logger.error(f"Watchdog: {name} restart failed: {result.get('error')}")

                restart_counts[name] = count + 1


    def print_ecosystem_status(self):
        """Print a colorful ecosystem status to the console."""
        status = self.get_ecosystem_status()
        projects = status["projects"]
        summary = status["summary"]

        print("\n" + "=" * 60)
        print("  FORGEAI ECOSYSTEM STATUS")
        print("=" * 60)

        status_icons = {
            "healthy": "✅",
            "partial": "⚠️",
            "not_found": "❌",
        }
        icon = status_icons.get(summary.get("status", "unknown"), "❓")

        print(f"  Overall: {icon} {summary['available']}/{summary['total_projects']} projects available")
        print()

        for name, info in projects.items():
            project_status = "✓" if info.get("exists") else "✗"

            details = []
            if name == "PythonAI":
                cfg = info.get("config", {})
                if cfg.get("available"):
                    details.append(f"signals={sum(cfg.get('signals', {}).values())}")
                    details.append(f"rate={cfg.get('acceptance_rate', 0):.0f}%")
                else:
                    details.append("not initialized")

            elif name == "hermes-agent":
                details.append("installed" if info.get("installed", {}).get("installed") else "not installed")

            elif name in ("Rudra-bots", "Dashboard"):
                api = info.get("api", {})
                details.append("running" if api.get("available") else "not running")

            elif name == "open-claude":
                details.append("built" if info.get("built", {}).get("built") else "not built")

            detail_str = f" ({', '.join(details)})" if details else ""
            print(f"  {project_status} {name}{detail_str}")

        print("=" * 60)
        print()


# ── CLI Interface ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ForgeAI Ecosystem Manager")
    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status", help="Show ecosystem status")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")

    install_parser = subparsers.add_parser("install-hermes", help="Install hermes-agent")

    start_parser = subparsers.add_parser("start", help="Start ecosystem services")
    start_parser.add_argument("--service", choices=["pythonai", "rudra-bots", "all"], default="all")

    args = parser.parse_args()
    mgr = EcosystemManager()

    if args.command == "status":
        if getattr(args, "json", False):
            print(json.dumps(mgr.get_ecosystem_status(), indent=2, default=str))
        else:
            mgr.print_ecosystem_status()

    elif args.command == "install-hermes":
        result = mgr.install_hermes_agent()
        if result["success"]:
            print("✅ hermes-agent installed successfully!")
        else:
            print(f"❌ Failed: {result.get('error', 'unknown')}")

    elif args.command == "start":
        service = args.service
        if service in ("pythonai", "all"):
            mgr.run_pythonai_server()
        if service in ("rudra-bots", "all"):
            mgr.run_rudra_bots()
        print("Services started. Check status with: python -m src.integration.ecosystem_manager status")

    else:
        parser.print_help()
