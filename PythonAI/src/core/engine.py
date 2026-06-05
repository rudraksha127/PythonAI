"""
PythonAI Core — Tool Calling Engine
=====================================
The central LLM + tools loop — PythonAI's 'QueryEngine'.
Inspired by Claude Code's QueryEngine.ts but built for Python + multi-provider.

Manages:
1. Sending messages + tool definitions to LLM
2. Parsing tool calls from response
3. Executing tools with validation + permissions
4. Feeding results back to LLM
5. Streaming responses
"""

from __future__ import annotations

import json
import time
import traceback
from typing import Any, Callable

from .tool import (
    Tool,
    ToolResult,
    ToolUseContext,
    PermissionDecision,
    ValidationResult,
)
from .registry import ToolRegistry, get_registry


# ═══════════════════════════════════════
#  Message Types
# ═══════════════════════════════════════

class Message:
    """A message in the conversation."""

    def __init__(self, role: str, content: str,
                 tool_calls: list[dict[str, Any]] | None = None,
                 tool_call_id: str | None = None,
                 name: str | None = None):
        self.role = role  # "system", "user", "assistant", "tool"
        self.content = content
        self.tool_calls = tool_calls  # For assistant messages
        self.tool_call_id = tool_call_id  # For tool result messages
        self.name = name  # For tool result messages

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible message dict."""
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg

    def to_anthropic_dict(self) -> dict[str, Any]:
        """Convert to Anthropic-compatible message dict."""
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        return msg


# ═══════════════════════════════════════
#  Tool Call Parser
# ═══════════════════════════════════════

def parse_tool_calls(response_text: str) -> list[dict[str, Any]]:
    """Parse tool calls from LLM response text.

    Supports both:
    - OpenAI format: {"name": "...", "arguments": {...}}
    - XML/function call format: <tool_call><tool_name>...</tool_name>...
    """
    tool_calls = []

    # Try JSON format first (OpenAI-style)
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            if "name" in data and "arguments" in data:
                tool_calls.append({
                    "id": f"call_{int(time.time()*1000)}",
                    "type": "function",
                    "function": {
                        "name": data["name"],
                        "arguments": json.dumps(data["arguments"])
                        if isinstance(data["arguments"], dict)
                        else data["arguments"],
                    }
                })
                return tool_calls
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    tool_calls.append(tc)
                return tool_calls
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    tool_calls.append({
                        "id": f"call_{int(time.time()*1000)}",
                        "type": "function",
                        "function": {
                            "name": item["name"],
                            "arguments": json.dumps(item.get("arguments", {})),
                        }
                    })
            return tool_calls
    except (json.JSONDecodeError, TypeError):
        pass

    # Try XML format
    import re
    xml_calls = re.findall(
        r'<(?:tool_call|invoke|use_tool)>'
        r'\s*<(?:tool_name|name)>(.*?)</(?:tool_name|name)>'
        r'\s*<(?:parameters|arguments|input)>(.*?)</(?:parameters|arguments|input)>'
        r'\s*</(?:tool_call|invoke|use_tool)>',
        response_text, re.DOTALL
    )
    for name, args_text in xml_calls:
        try:
            args = json.loads(args_text.strip())
        except json.JSONDecodeError:
            args = {"raw": args_text.strip()}
        tool_calls.append({
            "id": f"call_{int(time.time()*1000)}",
            "type": "function",
            "function": {
                "name": name.strip(),
                "arguments": json.dumps(args),
            }
        })

    # Try inline format: ToolName(param=value, param2=value2)
    if not tool_calls:
        inline_calls = re.findall(
            r'(?:Tool|tool):\s*(\w+)\s*\((.+?)\)\s*(?:\n|$)',
            response_text
        )
        for name, args_str in inline_calls:
            # Simple key=value parsing
            args = {}
            for kv in re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_str):
                args[kv[0]] = kv[1]
            tool_calls.append({
                "id": f"call_{int(time.time()*1000)}",
                "type": "function",
                "function": {
                    "name": name.strip(),
                    "arguments": json.dumps(args),
                }
            })

    return tool_calls


# ═══════════════════════════════════════
#  Tool Calling Engine
# ═══════════════════════════════════════

class ToolCallingEngine:
    """The central LLM + tools loop.

    Inspired by Claude Code's QueryEngine — manages the conversation loop
    where the LLM can call tools, get results, and continue reasoning.

    Supports:
    - Multiple LLM providers (OpenAI, Anthropic, Groq, local Ollama, etc.)
    - Tool validation and permissions
    - Streaming responses
    - Multi-turn conversations
    - Parallel tool execution
    """

    def __init__(self,
                 provider: str = "auto",
                 model: str = "",
                 registry: ToolRegistry | None = None,
                 max_tool_rounds: int = 25,
                 on_stream: Callable[[str], None] | None = None,
                 on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
                 on_tool_result: Callable[[str, Any], None] | None = None,
                 ):
        self.provider = provider
        self.model = model
        self.registry = registry or get_registry()
        self.max_tool_rounds = max_tool_rounds
        self.on_stream = on_stream
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result

        # Conversation history
        self.messages: list[Message] = []
        self.context = ToolUseContext()

        # Statistics
        self.stats = {
            "total_rounds": 0,
            "total_tool_calls": 0,
            "total_tokens": 0,
            "start_time": 0,
            "end_time": 0,
        }

    # ── Provider Methods ─────────────────────────────────────

    def _call_llm(self, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Call the LLM with messages and tools.

        Uses PythonAI's existing multi-provider LLM engine.
        """
        from src.utils.llm import generate_with_provider

        # Build system prompt with tool definitions
        system_prompt = self._build_system_prompt(tools)

        # Format messages for the provider
        prompt_parts = []
        for msg in messages:
            if msg["role"] == "system":
                continue  # System is sent separately
            if msg["role"] == "user":
                prompt_parts.append(f"User: {msg['content']}")
            elif msg["role"] == "assistant":
                prompt_parts.append(f"Assistant: {msg['content']}")
            elif msg["role"] == "tool":
                prompt_parts.append(
                    f"Tool Result ({msg.get('name', 'unknown')}): {msg['content']}")

        prompt = "\n\n".join(prompt_parts)

        # Call the LLM
        full_prompt = (
            f"{system_prompt}\n\n"
            f"Available tools:\n{self._format_tools_for_prompt(tools)}\n\n"
            f"Conversation:\n{prompt}\n\n"
            f"Assistant:"
        )

        response = generate_with_provider(
            full_prompt,
            provider=self.provider,
            system_prompt=system_prompt,
        )

        return {
            "content": response,
            "tool_calls": [],
        }

    def _call_llm_stream(self, messages: list[dict[str, Any]],
                          tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Call the LLM with streaming."""
        # For now, non-streaming fallback
        return self._call_llm(messages, tools)

    # ── System Prompt Builder ────────────────────────────────

    def _build_system_prompt(self, tools: list[dict[str, Any]]) -> str:
        """Build the system prompt with tool descriptions."""
        return f"""You are PythonAI — an elite AI coding assistant with access to powerful tools.

You have access to the following tools. When you need to use a tool, respond with a JSON tool call:

Available tools:
{self._format_tools_for_prompt(tools)}

To use a tool, respond with JSON in this format:
{{"name": "tool_name", "arguments": {{"param1": "value1", "param2": "value2"}}}}

Or you can use XML format:
<tool_call>
<tool_name>tool_name</tool_name>
<parameters>
{{"param1": "value1"}}
</parameters>
</tool_call>

After receiving tool results, use them to continue your response.
Think step by step about which tools to use and in what order.
Always provide helpful, accurate responses to the user.
"""

    def _format_tools_for_prompt(self, tools: list[dict[str, Any]]) -> str:
        """Format tools for the system prompt."""
        parts = []
        for tool in tools:
            name = tool.get("function", tool).get("name", "unknown")
            desc = tool.get("function", tool).get("description", "")
            params = tool.get("function", tool).get("parameters", {})
            props = params.get("properties", {})

            param_lines = []
            for pname, pinfo in props.items():
                required = pname in params.get("required", [])
                req_mark = " (required)" if required else ""
                param_lines.append(f"    {pname}: {pinfo.get('type', 'any')}{req_mark} - {pinfo.get('description', '')}")

            parts.append(f"  - {name}: {desc}")
            if param_lines:
                parts.append("    Parameters:")
                parts.extend(param_lines)

        return "\n".join(parts)

    # ── Tool Execution ───────────────────────────────────────

    def _execute_tool(self, tool_call: dict[str, Any]) -> str:
        """Execute a single tool call and return the result."""
        fn_info = tool_call.get("function", tool_call)
        name = fn_info.get("name", "")
        args_str = fn_info.get("arguments", "{}")

        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {"raw_input": args_str}

        # Find the tool
        tool = self.registry.get(name)
        if not tool:
            return json.dumps({"error": f"Tool '{name}' not found. Available: {[t.name for t in self.registry.list_all()]}"})

        # Validate input
        validation = tool.validate_input(args, self.context)
        if not validation.success:
            return json.dumps({"error": f"Validation failed: {validation.message}"})

        # Check permissions
        permission = tool.check_permissions(args, self.context)
        if permission.behavior in (PermissionDecision.DENY,
                                    PermissionDecision.ALWAYS_DENY):
            return json.dumps({"error": f"Permission denied: {permission.message}"})

        # Notify
        if self.on_tool_call:
            self.on_tool_call(name, args)

        # Execute
        try:
            result = tool.call(args, self.context)

            self.stats["total_tool_calls"] += 1

            if self.on_tool_result:
                self.on_tool_result(name, result.data)

            if result.error:
                return json.dumps({"error": result.error})
            if isinstance(result.data, str):
                return result.data
            return json.dumps(result.data, default=str, ensure_ascii=False)

        except Exception as e:
            tb = traceback.format_exc()
            return json.dumps({
                "error": f"Tool execution failed: {e}",
                "traceback": tb[-500:],
            })

    def _execute_parallel_tools(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute multiple tool calls, possibly in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        for tc in tool_calls:
            result = self._execute_tool(tc)
            fn_info = tc.get("function", tc)
            results.append({
                "tool_call_id": tc.get("id", "call_unknown"),
                "name": fn_info.get("name", "unknown"),
                "content": result,
            })
        return results

    # ── Main Loop ────────────────────────────────────────────

    def run(self, user_input: str,
            system_prompt: str | None = None,
            tools: list[Tool] | None = None,
            stream: bool = False) -> str:
        """Run the tool-calling loop with a user input.

        Args:
            user_input: The user's message.
            system_prompt: Optional override system prompt.
            tools: Optional list of tools to use (default: all registered).
            stream: Whether to stream the response.

        Returns:
            The final assistant response.
        """
        self.stats["start_time"] = time.time()
        self.stats["total_rounds"] = 0

        # Get tools
        if tools is None:
            tools = self.registry.list_all()

        # Convert tools to API format
        tool_defs = [t.to_openai_tool() for t in tools]

        # Add user message
        self.messages.append(Message("user", user_input))

        # Tool-calling loop
        for round_num in range(self.max_tool_rounds):
            self.stats["total_rounds"] = round_num + 1

            # Build message list
            msg_dicts = []
            for m in self.messages:
                msg_dicts.append(m.to_dict())

            # Call LLM
            response = self._call_llm(msg_dicts, tool_defs)

            response_text = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            # Parse tool calls from response text
            if not tool_calls and response_text:
                parsed = parse_tool_calls(response_text)
                if parsed:
                    tool_calls = parsed
                    response_text = ""  # Tool calls consumed the response

            # Stream text
            if response_text and self.on_stream:
                self.on_stream(response_text)

            # If no tool calls, we're done
            if not tool_calls:
                self.messages.append(Message("assistant", response_text))
                break

            # Execute tool calls
            self.messages.append(Message("assistant", response_text or "",
                                          tool_calls=tool_calls))

            tool_results = self._execute_parallel_tools(tool_calls)

            # Add tool results to messages
            for tr in tool_results:
                self.messages.append(Message(
                    role="tool",
                    content=tr["content"],
                    tool_call_id=tr["tool_call_id"],
                    name=tr["name"],
                ))

        self.stats["end_time"] = time.time()

        # Return the final assistant response
        assistant_messages = [m for m in self.messages if m.role == "assistant"]
        return assistant_messages[-1].content if assistant_messages else response_text

    def stream_run(self, user_input: str, **kwargs) -> str:
        """Run with streaming."""
        return self.run(user_input, stream=True, **kwargs)

    def reset(self) -> None:
        """Reset the conversation."""
        self.messages = []
        self.stats = {k: 0 if isinstance(v, int) else v
                      for k, v in self.stats.items()}

    def get_stats_report(self) -> dict[str, Any]:
        """Get execution statistics."""
        elapsed = self.stats.get("end_time", time.time()) - self.stats.get("start_time", time.time())
        return {
            "total_rounds": self.stats["total_rounds"],
            "total_tool_calls": self.stats["total_tool_calls"],
            "total_tokens": self.stats["total_tokens"],
            "elapsed_seconds": round(elapsed, 2),
            "messages_count": len(self.messages),
        }
