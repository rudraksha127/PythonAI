"""
PythonAI Test MCP Server
=========================
A simple MCP protocol server implemented in pure Python (no dependencies).
Exposes 3 tools: echo, greet, reverse_string.

Implements JSON-RPC 2.0 over stdio with the MCP protocol:
  1. initialize / initialized handshake
  2. tools/list — returns available tools
  3. tools/call — executes a tool and returns results
  4. ping — keepalive

Usage:
    python test_mcp_server.py
    # Reads JSON-RPC from stdin, writes responses to stdout
"""

import json
import sys

# ─────────────────────────────────────────────
#  Tool Implementations
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "echo",
        "description": "Echo back the input message",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "The message to echo back"}},
            "required": ["message"],
        },
    },
    {
        "name": "greet",
        "description": "Generate a personalized greeting",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the person to greet"},
                "title": {"type": "string", "description": "Optional title (Mr., Dr., etc.)"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "reverse_string",
        "description": "Reverse a string input",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The text to reverse"}},
            "required": ["text"],
        },
    },
    {
        "name": "add_numbers",
        "description": "Add two numbers together",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
    },
]


def handle_initialize(params):
    """Handle MCP initialize request."""
    params.get("protocolVersion", "2025-03-26")
    return {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {}, "resources": {}},
        "serverInfo": {"name": "pythonai-test-mcp", "version": "1.0.0"},
    }


def handle_tools_list(params):
    """Handle tools/list request."""
    return {"tools": TOOLS}


def handle_tools_call(params):
    """Handle tools/call request."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name == "echo":
        message = arguments.get("message", "")
        return {"content": [{"type": "text", "text": f"Echo: {message}"}]}

    elif tool_name == "greet":
        name = arguments.get("name", "World")
        title = arguments.get("title", "")
        prefix = f"{title} " if title else ""
        return {"content": [{"type": "text", "text": f"Hello, {prefix}{name}! Welcome to PythonAI MCP."}]}

    elif tool_name == "reverse_string":
        text = arguments.get("text", "")
        reversed_text = text[::-1]
        return {"content": [{"type": "text", "text": f"Original: {text}\nReversed: {reversed_text}"}]}

    elif tool_name == "add_numbers":
        a = arguments.get("a", 0)
        b = arguments.get("b", 0)
        result = a + b
        return {"content": [{"type": "text", "text": f"{a} + {b} = {result}"}]}

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def handle_ping(params):
    """Handle ping request."""
    return {}


# ─────────────────────────────────────────────
#  Request Router
# ─────────────────────────────────────────────

HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "ping": handle_ping,
}


def handle_message(message):
    """Process an incoming JSON-RPC message and return a response."""
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params", {}) or {}

    # Show stderr for debugging on the client side
    if msg_id is not None:
        print(f"[MCP Server] Handling: {method}", file=sys.stderr, flush=True)

    # Notification (no id) — no response expected
    if msg_id is None:
        if method == "notifications/initialized":
            print("[MCP Server] Client initialized notification", file=sys.stderr, flush=True)
        elif method == "initialized":
            print("[MCP Server] Client initialized", file=sys.stderr, flush=True)
        return None

    try:
        handler = HANDLERS.get(method)
        if handler is None:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

        result = handler(params)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    except ValueError as e:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": str(e)}}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": f"Internal error: {e}"}}


# ─────────────────────────────────────────────
#  Main Loop
# ─────────────────────────────────────────────


def main():
    """Main loop: read JSON-RPC from stdin, write responses to stdout."""
    print("[MCP Server] Starting test MCP server...", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
            response = handle_message(message)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            error_response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()
            print(f"[MCP Server] Parse error: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[MCP Server] Error: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
