"""
Open-Claude Bridge — Connect PythonAI to Open-Claude CLI
===========================================================

Makes PythonAI available as a model provider inside open-claude CLI,
so users can use PythonAI's RAG engine, agents, and training from the terminal.

Architecture:
  PythonAI provides an OpenAI-compatible API endpoint at /v1/chat/completions
  open-claude connects to this endpoint as if it were any other LLM provider.

Usage:
  1. Start PythonAI API server:  python -m src.api.server --port 7337
  2. Configure open-claude:       openclaude provider add forgeai --base-url http://localhost:7337
  3. Use in open-claude:          openclaude --provider forgeai "your prompt"
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("forgeai.integration.open_claude")

DEFAULT_OPEN_CLAUDE_PORT = 7337


def is_open_claude_available() -> bool:
    """Check if open-claude is installed and accessible."""
    try:
        result = subprocess.run(
            ["openclaude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=True,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        result = subprocess.run(
            ["npx", "openclaude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_open_claude_version() -> str:
    """Get the installed open-claude version."""
    try:
        result = subprocess.run(
            ["openclaude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "not found"


def configure_open_claude_for_forgeai(api_port: int = DEFAULT_OPEN_CLAUDE_PORT) -> dict[str, Any]:
    """Add PythonAI as a provider in open-claude's configuration.

    Creates a provider profile that points open-claude to PythonAI's
    OpenAI-compatible API server.

    Args:
        api_port: Port where PythonAI API server is running

    Returns:
        Dict with result information
    """
    if not is_open_claude_available():
        return {"success": False, "error": "open-claude not installed"}

    provider_name = "forgeai"
    base_url = f"http://localhost:{api_port}"

    try:
        # Use open-claude's provider add command
        result = subprocess.run(
            [
                "openclaude",
                "provider",
                "add",
                provider_name,
                "--base-url",
                base_url,
                "--api-key",
                "forgeai-local",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            shell=True,
        )

        if result.returncode == 0:
            logger.info(f"open-claude configured with ForgeAI provider at {base_url}")
            return {
                "success": True,
                "provider": provider_name,
                "base_url": base_url,
                "message": result.stdout.strip(),
            }
        else:
            return {
                "success": False,
                "error": result.stderr.strip() or f"Exit code: {result.returncode}",
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Configuration timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "open-claude CLI not found in PATH"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_to_cli(command: str, args: dict[str, Any] | None = None) -> str:
    """Send a command to open-claude CLI for execution.

    Args:
        command: The open-claude command to run
        args: Optional arguments dict

    Returns:
        Command output as string
    """
    if args is None:
        args = {}

    cmd = ["openclaude", command]
    for key, value in args.items():
        cmd.extend([f"--{key}", str(value)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT: Command exceeded 30s"
    except FileNotFoundError:
        return "Error: open-claude not found"
    except Exception as e:
        return f"Error: {e}"


async def query_forgeai_chat(
    prompt: str,
    model: str = "default",
    api_port: int = DEFAULT_OPEN_CLAUDE_PORT,
) -> dict[str, Any]:
    """Send a chat query to PythonAI's RAG /ask endpoint.

    This calls PythonAI's existing /ask endpoint (RAG-powered Q&A).
    open-claude can route through this when configured with the
    'forgeai' provider pointing to PythonAI's API server.

    Args:
        prompt: The user's query
        model: Model name (default: forgeai)
        api_port: PythonAI API server port

    Returns:
        Dict with response and metadata
    """
    url = f"http://localhost:{api_port}/ask"
    payload = {"question": prompt, "model": model}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "answer": data.get("answer", ""),
                    "sources": data.get("sources", []),
                    "model": data.get("model", model),
                }
            return {
                "success": False,
                "error": f"API returned {response.status_code}",
                "detail": response.text,
            }
    except httpx.ConnectError:
        return {
            "success": False,
            "error": "PythonAI API server not running",
            "detail": f"Start with: python -m src.api.server --port {api_port}",
        }
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out after 60s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_cli_status() -> dict[str, Any]:
    """Get comprehensive open-claude status for the ecosystem dashboard."""
    return {
        "installed": is_open_claude_available(),
        "version": get_open_claude_version(),
        "provider_configured": False,  # Would need to check config
    }
