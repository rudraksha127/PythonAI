"""
PythonAI MCP — Client Connection Manager
=========================================
Connect to external MCP servers, fetch tools/resources, call tools.
Inspired by Claude Code's services/mcp/client.ts.

Supports transport types:
  - stdio: subprocess with JSON-RPC over stdin/stdout
  - sse:  Server-Sent Events with HTTP POST for requests
  - http: Streamable HTTP transport
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Any

import httpx

from .types import (
    ConnectionState,
    HTTPConfig,
    MCPResourceInfo,
    MCPToolInfo,
    MCPToolResult,
    ServerConfig,
    ServerConnection,
    SSEConfig,
    StdioConfig,
)

logger = logging.getLogger("pythonai.mcp")


# ═══════════════════════════════════════
#  MCP Client
# ═══════════════════════════════════════

class MCPClient:
    """Client for connecting to and communicating with MCP servers.

    Manages connection lifecycle, tool/resource discovery, and tool execution.
    Uses JSON-RPC 2.0 for message exchange.
    """

    def __init__(self, name: str = "pythonai", version: str = "1.0.0"):
        self.client_info = {"name": name, "version": version}
        self._pending_requests: dict[str, Any] = {}
        self._request_lock = threading.Lock()
        self._next_id_counter = 1
        self._connections: list[Any] = []
        self._capabilities: dict[str, Any] = {}
        self._instructions: str | None = None

    # ── Connection Methods ─────────────────────────────────────

    def connect_stdio(self, config: StdioConfig) -> ServerConnection:
        """Connect to an MCP server via stdio subprocess."""
        import subprocess as sp

        env = os.environ.copy()
        if config.env:
            env.update(config.env)

        try:
            proc = sp.Popen(
                [config.command, *config.args],
                stdin=sp.PIPE,
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                env=env,
                text=True,
            )
        except FileNotFoundError:
            return ServerConnection(
                name=config.command,
                state=ConnectionState.FAILED,
                config=config,
                error=f"Command not found: {config.command}",
            )

        transport = _StdioTransport(proc)
        conn = self._initialize(transport, config)
        self._connections.append(conn)
        return conn

    def connect_sse(self, config: SSEConfig) -> ServerConnection:
        """Connect to an MCP server via SSE transport."""
        transport = _SSETransport(config.url, config.headers or {})
        conn = self._initialize(transport, config)
        self._connections.append(conn)
        return conn

    def connect_http(self, config: HTTPConfig) -> ServerConnection:
        """Connect to an MCP server via Streamable HTTP."""
        transport = _HTTPTransport(config.url, config.headers or {})
        conn = self._initialize(transport, config)
        self._connections.append(conn)
        return conn

    def connect(self, config: ServerConfig, name: str = "") -> ServerConnection:
        """Connect to an MCP server with auto-detected transport type."""
        if isinstance(config, StdioConfig):
            conn = self.connect_stdio(config)
            if name:
                conn.name = name
            return conn
        elif isinstance(config, SSEConfig):
            conn = self.connect_sse(config)
            if name:
                conn.name = name
            return conn
        elif isinstance(config, HTTPConfig):
            conn = self.connect_http(config)
            if name:
                conn.name = name
            return conn
        else:
            return ServerConnection(
                name=name or "unknown",
                state=ConnectionState.FAILED,
                config=config,
                error=f"Unsupported transport type: {type(config).__name__}",
            )

    def close_all(self) -> None:
        """Close all active connections."""
        for conn in self._connections:
            try:
                if conn._transport:
                    conn._transport.close()
            except Exception:
                pass
        self._connections.clear()

    # ── Internal ───────────────────────────────────────────────

    def _initialize(self, transport: Any, config: ServerConfig, server_name: str = "") -> ServerConnection:
        """Perform MCP initialize handshake and return connection."""
        if not server_name:
            server_name = getattr(config, "command", getattr(config, "url", "mcp-server"))
            if not isinstance(server_name, str):
                server_name = "mcp-server"

        try:
            # Step 1: Send initialize request
            init_result = self._send_request(transport, "initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": self.client_info,
            })

            if not init_result:
                return ServerConnection(
                    name=server_name, state=ConnectionState.FAILED,
                    config=config, error="Initialize failed: no response",
                )

            self._capabilities = init_result.get("capabilities", {})
            server_info = init_result.get("serverInfo", {})

            # Step 2: Send initialized notification
            self._send_notification(transport, "initialized")

            # Step 3: Fetch tools and resources
            tools = self._fetch_tools(transport)
            resources = self._fetch_resources(transport)

            return ServerConnection(
                name=server_name,
                state=ConnectionState.CONNECTED,
                config=config,
                capabilities=self._capabilities,
                server_info=server_info,
                tools=tools,
                resources=resources,
                _transport=transport,
                _client=self,
            )

        except Exception as e:
            logger.error(f"MCP initialize failed for {server_name}: {e}")
            try:
                transport.close()
            except Exception:
                pass
            return ServerConnection(
                name=server_name,
                state=ConnectionState.FAILED,
                config=config,
                error=str(e),
            )

    def _fetch_tools(self, transport: Any) -> list[MCPToolInfo]:
        """Fetch available tools from the MCP server."""
        try:
            result = self._send_request(transport, "tools/list")
            if not result or "tools" not in result:
                return []

            tools = []
            for t in result["tools"]:
                tools.append(MCPToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    annotations=t.get("annotations", {}),
                ))
            return tools
        except Exception as e:
            logger.debug(f"Failed to fetch tools: {e}")
            return []

    def _fetch_resources(self, transport: Any) -> list[MCPResourceInfo]:
        """Fetch available resources from the MCP server."""
        try:
            result = self._send_request(transport, "resources/list")
            if not result or "resources" not in result:
                return []

            resources = []
            for r in result["resources"]:
                resources.append(MCPResourceInfo(
                    uri=r.get("uri", ""),
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                    mime_type=r.get("mimeType", ""),
                ))
            return resources
        except Exception as e:
            logger.debug(f"Failed to fetch resources: {e}")
            return []

    def call_tool(
        self,
        transport: Any,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> MCPToolResult:
        """Call a tool on the MCP server."""
        params: dict[str, Any] = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments

        try:
            result = self._send_request(transport, "tools/call", params, timeout=timeout)

            if result is None:
                return MCPToolResult(
                    content=[{"type": "text", "text": "Tool call failed: no response"}],
                    is_error=True,
                )

            content = result.get("content", [])
            is_error = result.get("isError", False)
            meta = result.get("_meta")

            return MCPToolResult(
                content=content,
                is_error=is_error,
                _meta=meta,
            )

        except Exception as e:
            return MCPToolResult(
                content=[{"type": "text", "text": f"Error calling tool '{tool_name}': {e}"}],
                is_error=True,
            )

    # ── JSON-RPC Message Handling ──────────────────────────────

    def _next_id(self) -> int:
        with self._request_lock:
            req_id = self._next_id_counter
            self._next_id_counter += 1
            return req_id

    def _send_request(
        self,
        transport: Any,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Send a JSON-RPC request and wait for response."""
        req_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params:
            message["params"] = params

        return transport.send_message(json.dumps(message), req_id, timeout)

    def _send_notification(self, transport: Any, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            message["params"] = params

        transport.send_notification(json.dumps(message))


# ═══════════════════════════════════════
#  Transport Implementations
# ═══════════════════════════════════════

class _StdioTransport:
    """JSON-RPC transport over stdio subprocess."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self._responses: dict[int, Any] = {}
        self._response_events: dict[int, threading.Event] = {}
        self._running = True
        # Drain stderr in a background thread to prevent pipe deadlocks
        # (npx prints install progress to stderr; if pipe fills, process hangs)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _drain_stderr(self) -> None:
        """Drain stderr to prevent pipe deadlocks."""
        try:
            for line in self.proc.stderr:
                logger.debug("MCP stderr: %s", line.rstrip())
        except Exception:
            pass

    def _read_loop(self) -> None:
        """Read JSON-RPC responses from stdout."""
        buffer = ""
        while self._running and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                buffer += line
                # Try to parse complete JSON objects
                while buffer.strip():
                    try:
                        obj = json.loads(buffer.strip())
                        buffer = ""
                        self._handle_message(obj)
                    except json.JSONDecodeError:
                        # Incomplete JSON, keep reading
                        break
            except Exception:
                break

    def _handle_message(self, msg: dict) -> None:
        """Handle incoming JSON-RPC message."""
        if "id" in msg and msg["id"] is not None:
            req_id = int(msg["id"])
            event = self._response_events.get(req_id)
            if event:
                self._responses[req_id] = msg
                event.set()

    def send_message(self, text: str, req_id: int, timeout: float = 30.0) -> Any:
        """Send a request and wait for response."""
        event = threading.Event()
        self._response_events[req_id] = event

        try:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
            event.wait(timeout=timeout)
            response = self._responses.pop(req_id, None)
            self._response_events.pop(req_id, None)
            if response and "error" in response and response["error"]:
                raise Exception(response["error"].get("message", "RPC error"))
            return response.get("result") if response else None
        finally:
            self._response_events.pop(req_id, None)
            self._responses.pop(req_id, None)

    def send_notification(self, text: str) -> None:
        """Send a notification without waiting for response."""
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        self._running = False
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class _SSETransport:
    """JSON-RPC transport over SSE (Server-Sent Events).

    MCP SSE spec:
      1. Client connects via GET to SSE endpoint
      2. Server sends 'endpoint' event with message POST URL
      3. Client sends JSON-RPC requests via POST to message URL
      4. Responses arrive as SSE events on the persistent connection
    """

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.message_url: str | None = None  # Received from SSE 'endpoint' event
        self._headers = headers or {}
        self._responses: dict[int, Any] = {}
        self._response_events: dict[int, threading.Event] = {}
        self._running = True
        self._sse_ready = threading.Event()  # Signaled when message_url received

        # Start SSE listener in background
        self._sse_thread = threading.Thread(target=self._sse_listen, daemon=True)
        self._sse_thread.start()

    def _sse_listen(self) -> None:
        """Listen for SSE events.

        Captures:
          - 'endpoint' event: provides the POST URL for sending messages
          - 'message' events: JSON-RPC responses/notifications
        """
        import urllib.request

        req = urllib.request.Request(
            self.url,
            headers={
                "Accept": "text/event-stream",
                **self._headers,
            },
        )
        try:
            response = urllib.request.urlopen(req, timeout=None)
            event_type = "message"
            for line_bytes in response:
                if not self._running:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()

                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data = line[6:]
                    if event_type == "endpoint":
                        self.message_url = data.strip()
                        self._sse_ready.set()
                        logger.debug(f"SSE endpoint received: {self.message_url}")
                    elif event_type == "message":
                        try:
                            msg = json.loads(data)
                            self._handle_message(msg)
                        except json.JSONDecodeError:
                            pass
                    event_type = "message"
                elif line == "":
                    pass  # Empty line = event separator
        except Exception as e:
            logger.debug(f"SSE listener stopped: {e}")
            self._sse_ready.set()  # Unblock any waiting senders

    def _handle_message(self, msg: dict) -> None:
        if "id" in msg and msg["id"] is not None:
            req_id = int(msg["id"])
            event = self._response_events.get(req_id)
            if event:
                self._responses[req_id] = msg
                event.set()

    def send_message(self, text: str, req_id: int, timeout: float = 30.0) -> Any:
        """Send JSON-RPC via POST to the SSE message endpoint.

        Waits for the 'endpoint' event if not yet received, then
        POSTs the request. First checks if the POST response body
        contains a JSON-RPC result (synchronous response), and
        falls back to waiting for an SSE event (async response).
        """
        # Wait for message URL to be available
        if not self._sse_ready.wait(timeout=timeout):
            raise TimeoutError("SSE endpoint not received from server")

        if not self.message_url:
            raise ConnectionError("No SSE message endpoint URL available")

        event = threading.Event()
        self._response_events[req_id] = event

        import urllib.error
        import urllib.request

        try:
            data_bytes = text.encode("utf-8")
            req = urllib.request.Request(
                self.message_url,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    **self._headers,
                },
                method="POST",
            )
            try:
                resp = urllib.request.urlopen(req, timeout=timeout)
                body = resp.read().decode("utf-8", errors="replace")
                if body.strip():
                    # Synchronous JSON-RPC response in POST body
                    try:
                        msg = json.loads(body)
                        if "error" in msg and msg["error"]:
                            raise Exception(msg["error"].get("message", "RPC error"))
                        return msg.get("result")
                    except json.JSONDecodeError:
                        pass
            except urllib.error.HTTPError as e:
                # For 202 Accepted, the response comes via SSE stream
                if e.code == 202:
                    pass  # Wait for SSE event below
                else:
                    raise

            # Fallback: wait for response via SSE event
            event.wait(timeout=timeout)
            msg = self._responses.pop(req_id, None)
            self._response_events.pop(req_id, None)
            if msg and "error" in msg and msg["error"]:
                raise Exception(msg["error"].get("message", "RPC error"))
            return msg.get("result") if msg else None

        except urllib.error.HTTPError as e:
            error_text = e.read().decode("utf-8", errors="replace")
            raise Exception(f"HTTP {e.code}: {error_text}")
        finally:
            self._response_events.pop(req_id, None)
            self._responses.pop(req_id, None)

    def send_notification(self, text: str) -> None:
        if not self.message_url:
            return
        import urllib.request
        try:
            data_bytes = text.encode("utf-8")
            req = urllib.request.Request(
                self.message_url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5.0)
        except Exception:
            pass

    def close(self) -> None:
        self._running = False
        self._sse_ready.set()


class _HTTPTransport:
    """Streamable HTTP JSON-RPC transport."""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.session = httpx.Client(timeout=httpx.Timeout(60.0))
        self._headers = headers or {}

    def send_message(self, text: str, req_id: int, timeout: float = 30.0) -> Any:
        """Send request via HTTP POST, parse SSE or JSON response."""
        response = self.session.post(
            self.url,
            content=text,
            headers={
                **self._headers,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=httpx.Timeout(timeout),
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE response
            data = response.text
            for line in data.split("\n"):
                if line.startswith("data: "):
                    msg = json.loads(line[6:])
                    break
            else:
                msg = json.loads(data)
        else:
            msg = response.json()

        if "error" in msg and msg["error"]:
            raise Exception(msg["error"].get("message", "RPC error"))
        return msg.get("result")

    def send_notification(self, text: str) -> None:
        self.session.post(
            self.url,
            content=text,
            headers={**self._headers, "Content-Type": "application/json"},
            timeout=httpx.Timeout(5.0),
        )

    def close(self) -> None:
        self.session.close()


# ═══════════════════════════════════════
#  Convenience Functions
# ═══════════════════════════════════════

def connect_stdio(config: StdioConfig) -> ServerConnection:
    """Quick-connect to a stdio MCP server."""
    client = MCPClient()
    return client.connect_stdio(config)


def connect_sse(config: SSEConfig) -> ServerConnection:
    """Quick-connect to an SSE MCP server."""
    client = MCPClient()
    return client.connect_sse(config)


def call_tool(
    connection: ServerConnection,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> MCPToolResult:
    """Call a tool on an already-connected MCP server."""
    if connection.state != ConnectionState.CONNECTED:
        return MCPToolResult(
            content=[{"type": "text", "text": "Server not connected"}],
            is_error=True,
        )
    client = connection._client
    if client is None:
        return MCPToolResult(
            content=[{"type": "text", "text": "No client reference"}],
            is_error=True,
        )
    transport = connection._transport
    if transport is None:
        return MCPToolResult(
            content=[{"type": "text", "text": "No transport reference"}],
            is_error=True,
        )
    return client.call_tool(transport, tool_name, arguments)


def list_tools(connection: ServerConnection) -> list[MCPToolInfo]:
    """List available tools from a connected MCP server."""
    if connection.state != ConnectionState.CONNECTED:
        return []
    return connection.tools
