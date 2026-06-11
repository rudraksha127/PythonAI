"""
PythonAI MCP — Server
======================
PythonAI acting as an MCP server — expose built-in tools via the MCP protocol.
Allows external clients (Claude Code, Cursor, etc.) to call PythonAI tools.

Implements the MCP specification:
  - JSON-RPC 2.0 message exchange
  - Initialize / initialized handshake
  - tools/list, tools/call
  - resources/list, resources/read
  - Ping keepalive
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("pythonai.mcp.server")


# ═══════════════════════════════════════
#  MCP Server
# ═══════════════════════════════════════


class MCPServer:
    """MCP protocol server that exposes PythonAI tools.

    Can run in two modes:
      - stdio mode: JSON-RPC over stdin/stdout (for Claude Code integration)
      - sse mode: HTTP server with SSE transport
    """

    def __init__(
        self,
        name: str = "pythonai",
        version: str = "2.0.0",
        get_tools_fn: Callable[[], list[dict[str, Any]]] | None = None,
        server_info: dict[str, str] | None = None,
    ):
        self.server_info = {
            "name": name,
            "version": version,
            **(server_info or {}),
        }
        self._capabilities = {
            "tools": {},
            "resources": {},
        }
        self._get_tools_fn = get_tools_fn or (lambda: [])
        self._tools_cache: list[dict[str, Any]] = []

    def refresh_tools(self) -> None:
        """Refresh the tool cache from the registered function."""
        self._tools_cache = self._get_tools_fn()

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        """Get tools in MCP format for tools/list response."""
        self.refresh_tools()
        mcp_tools = []
        for tool in self._tools_cache:
            input_schema = tool.get("input_schema", tool.get("inputSchema", {}))
            if isinstance(input_schema, dict) and "type" not in input_schema:
                input_schema = {"type": "object", "properties": input_schema}

            mcp_tool = {
                "name": tool.get("name", "unknown"),
                "description": tool.get("description", ""),
                "inputSchema": input_schema,
            }
            # Annotations from tool def
            annotations = {}
            if tool.get("is_readonly"):
                annotations["readOnlyHint"] = True
            if tool.get("is_destructive"):
                annotations["destructiveHint"] = True
            if annotations:
                mcp_tool["annotations"] = annotations

            mcp_tools.append(mcp_tool)
        return mcp_tools

    # ── Request Handlers ───────────────────────────────────────

    def handle_request(self, message: dict) -> dict | None:
        """Handle an incoming JSON-RPC request.

        Returns the response dict, or None for notifications.
        """
        method = message.get("method", "")
        req_id = message.get("id")
        params = message.get("params", {}) or {}

        is_notification = req_id is None
        if is_notification:
            self._handle_notification(method, params)
            return None

        try:
            result = self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            logger.error(f"MCP request failed: {method}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32603,
                    "message": str(e),
                },
            }

    def _dispatch(self, method: str, params: dict) -> Any:
        """Dispatch a request to the appropriate handler."""
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": lambda p: {},
        }

        handler = handlers.get(method)
        if handler is None:
            raise ValueError(f"Unknown method: {method}")

        return handler(params)

    def _handle_notification(self, method: str, params: dict) -> None:
        """Handle a notification (no response expected)."""
        if method == "initialized":
            logger.debug("MCP client initialized")
        elif method == "notifications/initialized":
            logger.debug("MCP client initialized (notification)")
        elif method == "$/cancelRequest":
            logger.debug("Cancel request received")

    def _handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", "2025-03-26")
        logger.info(
            f"MCP client connected: {client_info.get('name', 'unknown')} "
            f"v{client_info.get('version', '?')} "
            f"(protocol: {protocol_version})"
        )
        return {
            "protocolVersion": "2025-03-26",
            "capabilities": self._capabilities,
            "serverInfo": self.server_info,
        }

    def _handle_tools_list(self, params: dict) -> dict:
        """Handle tools/list request."""
        return {"tools": self.get_mcp_tools()}

    def _handle_tools_call(self, params: dict) -> dict:
        """Handle tools/call request — execute a tool and return results."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Ensure tools cache is fresh
        self.refresh_tools()

        # Find the tool
        for tool in self._tools_cache:
            if tool.get("name") == tool_name:
                call_fn = tool.get("call")
                if call_fn is None:
                    raise ValueError(f"Tool '{tool_name}' has no call function")

                # Execute the tool
                from ..tool import ToolUseContext

                context = ToolUseContext(cwd=os.getcwd())
                result = call_fn(arguments, context)

                if result.error:
                    return {
                        "content": [{"type": "text", "text": result.error}],
                        "isError": True,
                    }

                # Format result as MCP content
                data = result.data
                if isinstance(data, dict) and "text" in data:
                    content = [{"type": "text", "text": data["text"]}]
                elif isinstance(data, dict) and "content" in data:
                    content = data["content"]
                else:
                    content = [{"type": "text", "text": str(data)}]

                return {"content": content}

        raise ValueError(f"Unknown tool: {tool_name}")

    def _handle_resources_list(self, params: dict) -> dict:
        """Handle resources/list request."""
        return {"resources": []}

    def _handle_resources_read(self, params: dict) -> dict:
        """Handle resources/read request."""
        raise ValueError("No resources available")


# ═══════════════════════════════════════
#  Server Launchers
# ═══════════════════════════════════════


def create_mcp_app(get_tools_fn: Callable[[], list[dict[str, Any]]]) -> MCPServer:
    """Create an MCP server instance with tool discovery function."""
    return MCPServer(get_tools_fn=get_tools_fn)


def start_mcp_server_stdio(server: MCPServer) -> None:
    """Run MCP server in stdio mode (reads from stdin, writes to stdout).

    Implements JSON-RPC 2.0 over stdin/stdout with newline-delimited JSON.
    Stderr is used for logging.
    """
    logger.info("Starting MCP server in stdio mode")
    server.refresh_tools()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
            response = server.handle_request(message)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {e}",
                },
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error handling message: {e}")


def start_mcp_server_sse(
    server: MCPServer,
    host: str = "127.0.0.1",
    port: int = 8766,
) -> None:
    """Run MCP server in SSE mode (HTTP server with SSE transport).

    Minimal HTTP server for MCP SSE transport.
    """
    import http.server
    import urllib.parse

    server.refresh_tools()
    logger.info(f"Starting MCP SSE server on {host}:{port}")

    class MCPHTTPHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug(f"MCP HTTP: {args[0]} {args[1]} {args[2]}")

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/sse":
                self._handle_sse()
            else:
                self.send_error(404)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/message":
                self._handle_message()
            else:
                self.send_error(404)

        def _handle_sse(self):
            """Handle SSE connection."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Send endpoint event
            endpoint = f"http://{host}:{port}/message"
            self.wfile.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())
            self.wfile.flush()

            # Wait for client to close
            while True:
                try:
                    line = self.rfile.readline()
                    if not line:
                        break
                except Exception:
                    break

        def _handle_message(self):
            """Handle POST message to /message."""
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

            try:
                message = json.loads(body)
                response = server.handle_request(message)
                if response is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(202)
                    self.end_headers()
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    httpd = http.server.HTTPServer((host, port), MCPHTTPHandler)
    logger.info(f"MCP SSE server ready at http://{host}:{port}/sse")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("MCP server stopped")
        httpd.shutdown()


def start_mcp_server(
    server: MCPServer,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8766,
) -> None:
    """Start the MCP server with the specified transport.

    Args:
        server: MCPServer instance
        transport: "stdio" for stdin/stdout, "sse" for HTTP SSE server
        host: Host for SSE mode
        port: Port for SSE mode
    """
    if transport == "stdio":
        start_mcp_server_stdio(server)
    elif transport == "sse":
        start_mcp_server_sse(server, host, port)
    else:
        raise ValueError(f"Unsupported transport: {transport}")
