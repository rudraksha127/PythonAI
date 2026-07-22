"""
PythonAI Agentic System — SubAgent
====================================
An independent LLM + tool loop that executes sub-tasks with its own
tool pool, context window, and conversation history.

Each SubAgent:
  - Has a specialized role (coding, research, mcp, review)
  - Gets its own tool subset from the registry
  - Runs its own ToolCallingEngine for multi-step reasoning
  - Reports results back to the Orchestrator
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ── Constants ────────────────────────────────────────────────

MAX_LLM_RETRIES = 2
"""Number of times to retry a failed LLM API call."""

RETRY_DELAY_SECONDS = 1.0
"""Base delay in seconds before retrying (exponential backoff)."""

RETRY_JITTER = 0.5
"""Jitter factor for retry delay (±50%). Adds randomness to prevent thundering herd
when multiple sub-agents retry simultaneously. E.g., a 2.0s delay becomes 1.0-3.0s."""

from ..registry import ToolRegistry, get_registry  # noqa: E402
from ..tool import Tool, ToolUseContext  # noqa: E402


@dataclass
class SubAgentResult:
    """Result from a SubAgent execution."""

    agent_name: str
    role: str
    success: bool
    output: str
    tool_calls_used: int = 0
    rounds: int = 0
    tokens_used: int = 0
    elapsed: float = 0.0
    error: str | None = None


class SubAgent:
    """An independent sub-agent with its own LLM + tool loop.

    Each SubAgent:
      - Has a role (coding, research, mcp, review)
      - Gets a filtered tool pool from the registry
      - Runs ToolCallingEngine-style multi-step reasoning
      - Reports structured results
    """

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        tool_names: list[str] | None = None,
        tool_categories: list[str] | None = None,
        max_steps: int = 10,
        max_tool_calls: int = 4,
        max_retries: int = MAX_LLM_RETRIES,
        registry: ToolRegistry | None = None,
        call_llm_fn: Callable[..., Any] | None = None,
        on_stream: Callable[[str], None] | None = None,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_retries = max_retries
        self.registry = registry or get_registry()
        self.call_llm_fn = call_llm_fn
        self.on_stream = on_stream

        # Build tool pool
        if tool_names:
            self.tools = [t for t in self.registry.list_all() if t.name in tool_names]
        elif tool_categories:
            self.tools = [t for t in self.registry.list_all() if any(cat in t.name for cat in tool_categories)]
        else:
            self.tools = self.registry.list_builtin()

        # MCP tools
        self._mcp_tools = self.registry.list_mcp()

        # Conversation
        self.messages: list[dict[str, Any]] = []
        self.context = ToolUseContext()

        # Stats
        self.stats = {
            "tool_calls": 0,
            "rounds": 0,
            "tokens": 0,
        }
        self._last_llm_error: str | None = None

    # ── Role presets ─────────────────────────────────────────

    @classmethod
    def coding_agent(
        cls,
        registry: ToolRegistry | None = None,
        **kwargs: Any,
    ) -> SubAgent:
        """Create a coding-focused sub-agent."""
        return cls(
            name=kwargs.get("name", "coder"),
            role="coding",
            system_prompt=kwargs.get(
                "system_prompt",
                """You are a Python coding specialist. Write clean, idiomatic code.
Use file read/write/edit tools to implement solutions.
Always test your code with the bash tool before declaring done.
Explain your reasoning briefly before each tool use.

IMPORTANT: After 2-3 tool calls (read, write, test), stop and provide
your final answer. Do NOT continue making tool calls indefinitely.""",
            ),
            tool_names=kwargs.get("tool_names")
            or [
                "read",
                "write",
                "edit",
                "bash",
                "glob",
                "grep",
            ],
            registry=registry,
            call_llm_fn=kwargs.get("call_llm_fn"),
            on_stream=kwargs.get("on_stream"),
            max_steps=kwargs.get("max_steps", 15),
            max_tool_calls=kwargs.get("max_tool_calls", 4),
            max_retries=kwargs.get("max_retries", MAX_LLM_RETRIES),
        )

    @classmethod
    def research_agent(
        cls,
        registry: ToolRegistry | None = None,
        **kwargs: Any,
    ) -> SubAgent:
        """Create a research-focused sub-agent."""
        return cls(
            name=kwargs.get("name", "researcher"),
            role="research",
            system_prompt=kwargs.get(
                "system_prompt",
                """You are a research specialist. Use read-only tools to gather information.
Search files with grep/glob, read files to understand code, and use web tools.
Compile your findings into a clear summary. Do NOT modify any files.

IMPORTANT: After 2-3 tool calls, stop and provide your final summary.
Do NOT continue searching once you have sufficient information.""",
            ),
            tool_names=kwargs.get("tool_names")
            or [
                "read",
                "glob",
                "grep",
                "web_fetch",
                "web_search",
            ],
            registry=registry,
            call_llm_fn=kwargs.get("call_llm_fn"),
            on_stream=kwargs.get("on_stream"),
            max_steps=kwargs.get("max_steps", 10),
            max_tool_calls=kwargs.get("max_tool_calls", 4),
            max_retries=kwargs.get("max_retries", MAX_LLM_RETRIES),
        )

    @classmethod
    def mcp_agent(
        cls,
        registry: ToolRegistry | None = None,
        **kwargs: Any,
    ) -> SubAgent:
        """Create an MCP-tool-focused sub-agent."""
        return cls(
            name=kwargs.get("name", "mcp-worker"),
            role="mcp",
            system_prompt=kwargs.get(
                "system_prompt",
                """You are an MCP tool specialist. Use external MCP server tools
to interact with services like filesystem, databases, and APIs.
Explain what you're doing before each tool call.

IMPORTANT: After 2-3 tool calls, stop and provide your final answer.
Do NOT continue making tool calls once you have the information you need.""",
            ),
            tool_categories=kwargs.get("tool_categories") or ["mcp"],
            registry=registry,
            call_llm_fn=kwargs.get("call_llm_fn"),
            on_stream=kwargs.get("on_stream"),
            max_steps=kwargs.get("max_steps", 10),
            max_tool_calls=kwargs.get("max_tool_calls", 4),
            max_retries=kwargs.get("max_retries", MAX_LLM_RETRIES),
        )

    @classmethod
    def review_agent(
        cls,
        registry: ToolRegistry | None = None,
        **kwargs: Any,
    ) -> SubAgent:
        """Create a code review sub-agent."""
        return cls(
            name=kwargs.get("name", "reviewer"),
            role="review",
            system_prompt=kwargs.get(
                "system_prompt",
                """You are a senior code reviewer. Review code for:
1. Correctness — does it work correctly?
2. Edge cases — are there any unhandled scenarios?
3. Style — does it follow Python best practices?
Use read tools to examine the code, then provide concise feedback.

IMPORTANT: After 1-2 read tool calls, stop and provide your review.
Do NOT keep reading more files once you have enough context.""",
            ),
            tool_names=kwargs.get("tool_names") or ["read", "glob", "grep"],
            registry=registry,
            call_llm_fn=kwargs.get("call_llm_fn"),
            on_stream=kwargs.get("on_stream"),
            max_steps=kwargs.get("max_steps", 5),
            max_tool_calls=kwargs.get("max_tool_calls", 4),
            max_retries=kwargs.get("max_retries", MAX_LLM_RETRIES),
        )

    # ── Execution ────────────────────────────────────────────

    def run(self, task: str, context: str | None = None) -> SubAgentResult:
        """Execute the sub-agent on a task.

        Args:
            task: The sub-task description.
            context: Optional context from other agents.

        Returns:
            SubAgentResult with output and stats.
        """
        start_time = time.time()
        self.messages = []

        # Build system prompt with tools
        sys_msg = self._build_system_prompt(task, context)
        self.messages.append({"role": "system", "content": sys_msg})

        # Add user task
        user_content = task
        if context:
            user_content = f"Context from other agents:\n{context}\n\n---\n\n{task}"
        self.messages.append({"role": "user", "content": user_content})

        tool_defs = [t.to_openai_tool() for t in self._get_tool_pool()]

        # Multi-step reasoning loop
        for step in range(self.max_steps):
            self.stats["rounds"] = step + 1

            # Call LLM
            response = self._call_llm(self.messages, tool_defs)
            if not response:
                elapsed = time.time() - start_time
                error_msg = self._last_llm_error or "LLM call returned empty (no error details)"
                return SubAgentResult(
                    agent_name=self.name,
                    role=self.role,
                    success=False,
                    output="",
                    error=error_msg,
                    tool_calls_used=self.stats["tool_calls"],
                    rounds=self.stats["rounds"],
                    tokens_used=self.stats["tokens"],
                    elapsed=elapsed,
                )

            response_text = response.get("content", "")

            # Parse tool calls
            from ..executor import parse_tool_calls

            tool_calls = response.get("tool_calls", [])
            parsed = parse_tool_calls(response_text) if not tool_calls and response_text else []

            if tool_calls or parsed:
                tool_calls = tool_calls or parsed
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": response_text or "",
                        "tool_calls": tool_calls,
                    }
                )

                # Execute each tool call
                for tc in tool_calls:
                    result_content = self._execute_tool(tc)
                    fn_info = tc.get("function", tc)
                    self.messages.append(
                        {
                            "role": "tool",
                            "content": result_content,
                            "tool_call_id": tc.get("id", "call_unknown"),
                            "name": fn_info.get("name", "unknown"),
                        }
                    )
                    self.stats["tool_calls"] += 1

                    if self.on_stream:
                        self.on_stream(f"\n  [{self.name}] Tool: {fn_info.get('name', 'unknown')} -> done\n")

                # Safety check: enforce max_tool_calls limit
                if self.stats["tool_calls"] >= self.max_tool_calls:
                    # Force final answer: call LLM one more time WITHOUT tools
                    if self.on_stream:
                        self.on_stream(f"\n  [{self.name}] Max tools reached, synthesizing...\n")
                    final_response = self._call_llm(self.messages, [])
                    if final_response:
                        final_text = final_response.get("content", "")
                        if final_text:
                            return SubAgentResult(
                                agent_name=self.name,
                                role=self.role,
                                success=True,
                                output=final_text,
                                tool_calls_used=self.stats["tool_calls"],
                                rounds=self.stats["rounds"],
                                tokens_used=self.stats["tokens"],
                                elapsed=time.time() - start_time,
                            )
                    # Fallback: let the normal loop handle it
                    break

                continue  # Continue loop for next reasoning step

            # No tool calls — reasoning complete
            if response_text:
                self.messages.append({"role": "assistant", "content": response_text})
                if self.on_stream:
                    self.on_stream(f"\n  [{self.name}] Result: {response_text[:200]}...\n")

                return SubAgentResult(
                    agent_name=self.name,
                    role=self.role,
                    success=True,
                    output=response_text,
                    tool_calls_used=self.stats["tool_calls"],
                    rounds=self.stats["rounds"],
                    tokens_used=self.stats["tokens"],
                    elapsed=time.time() - start_time,
                )

            break  # Empty response

        return SubAgentResult(
            agent_name=self.name,
            role=self.role,
            success=True,
            output=self.messages[-1].get("content", "") if self.messages else "",
            tool_calls_used=self.stats["tool_calls"],
            rounds=self.stats["rounds"],
            tokens_used=self.stats["tokens"],
            elapsed=time.time() - start_time,
        )

    # ── Internal ─────────────────────────────────────────────

    def _get_tool_pool(self) -> list[Tool]:
        """Get the tool pool including MCP tools."""
        tools = list(self.tools)
        tools.extend(self._mcp_tools)
        return tools

    def _build_system_prompt(self, task: str, context: str | None = None) -> str:
        """Build system prompt with available tools and their parameter schemas."""
        tool_lines = []
        for t in self._get_tool_pool():
            tool_lines.append(f"  - {t.name}: {t.description}")
            schema = t.input_schema()
            # MCP tools return dict, regular tools return InputSchema
            if hasattr(schema, "parameters"):
                params = schema.parameters
            elif isinstance(schema, dict):
                params = schema.get("properties", {})
            else:
                params = {}
            if params:
                for pname, p_raw in params.items():
                    if hasattr(p_raw, "required"):
                        req = " (required)" if p_raw.required else ""
                        tool_lines.append(f"      {pname}: {p_raw.type}{req} - {p_raw.description}")
                    elif isinstance(p_raw, dict):
                        req = " (required)" if p_raw.get("required", False) else ""
                        ptype = p_raw.get("type", "any")
                        desc = p_raw.get("description", "")
                        tool_lines.append(f"      {pname}: {ptype}{req} - {desc}")

        return f"""{self.system_prompt}

You are the "{self.name}" agent with role "{self.role}".

Available tools:
{chr(10).join(tool_lines)}

To use a tool, respond with JSON:
{{"name": "tool_name", "arguments": {{"param1": "value1"}}}}

WORKFLOW:
1. Think about what information you need
2. Call 1-3 tools to gather that information
3. STOP making tool calls and provide your final answer

After calling 2-3 tools, you MUST stop and synthesize your findings
into a complete, well-structured final answer. Do NOT call more tools
once you have enough information."""

    def _call_llm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Call the LLM with retry and fallback support.

        Retries up to `self.max_retries` times on transient failures
        (network errors, rate limits, API errors) with exponential backoff.
        If the configured provider fails, falls back to the first available provider.

        Args:
            messages: The conversation messages.
            tools: Tool definitions for function calling.

        Returns:
            Response dict with "content" and "tool_calls" keys, or None on failure.
        """
        if self.call_llm_fn:
            return self.call_llm_fn(messages, tools)  # type: ignore[no-any-return]

        self._last_llm_error = None

        for attempt in range(self.max_retries + 1):
            try:
                from ..providers import ProfileManager, ProviderRouter, get_provider_api

                router = ProviderRouter()
                profile = ProfileManager().load()
                provider = profile.provider if profile else "auto"
                model = profile.model if profile else ""

                route = router.route(
                    provider=provider,
                    model=model,
                    task="coding",
                    require_function_calling=bool(tools),
                )

                if route.error:
                    # Fallback to first available
                    available = router.get_available_providers()
                    for p in available:
                        r = router.route(provider=p.id)
                        if not r.error:
                            route = r
                            break
                    else:
                        self._last_llm_error = f"No available providers: {route.error}"
                        if attempt < self.max_retries:
                            delay = (
                                RETRY_DELAY_SECONDS * (2**attempt) * (1 + random.uniform(-RETRY_JITTER, RETRY_JITTER))
                            )
                            if self.on_stream:
                                self.on_stream(
                                    f"\n  [{self.name}] Provider unavailable, retrying in {delay:.0f}s "
                                    f"({attempt + 1}/{self.max_retries})...\n"
                                )
                            time.sleep(delay)
                            continue
                        return None

                # Format messages
                formatted = []
                system_content = ""
                for msg in messages:
                    if msg["role"] == "system":
                        system_content = msg["content"]
                    elif msg["role"] == "tool":
                        formatted.append(
                            {
                                "role": "tool",
                                "content": msg["content"],
                                "tool_call_id": msg.get("tool_call_id", ""),
                                "name": msg.get("name", ""),
                            }
                        )
                    else:
                        entry: dict[str, Any] = {"role": msg["role"], "content": msg["content"]}
                        if msg.get("tool_calls"):
                            entry["tool_calls"] = msg["tool_calls"]
                        if msg.get("tool_call_id"):
                            entry["tool_call_id"] = msg["tool_call_id"]
                        if msg.get("name"):
                            entry["name"] = msg["name"]
                        formatted.append(entry)

                if system_content:
                    formatted.insert(0, {"role": "system", "content": system_content})

                # Call API with tool definitions for native function calling support
                api_fn = get_provider_api(route.provider)
                result = api_fn(
                    messages=formatted,
                    model=route.model,
                    base_url=route.base_url,
                    api_key=route.api_key or "",
                    temperature=0.3,
                    max_tokens=4096,
                    tools=tools if tools else None,
                )

                if result.get("error"):
                    self._last_llm_error = result["error"]
                    detail = result.get("error_detail", "")
                    if detail:
                        self._last_llm_error += f" | Detail: {detail[:200]}"
                    if attempt < self.max_retries:
                        delay = RETRY_DELAY_SECONDS * (2**attempt) * (1 + random.uniform(-RETRY_JITTER, RETRY_JITTER))
                        if self.on_stream:
                            err_msg = self._last_llm_error[:120]
                            self.on_stream(
                                f"\n  [{self.name}] API error: {err_msg}, "
                                f"retrying in {delay:.0f}s ({attempt + 1}/{self.max_retries})...\n"
                            )
                        time.sleep(delay)
                        continue
                    return None

                usage = result.get("usage", {})
                self.stats["tokens"] += usage.get("total_tokens", 0)

                return {
                    "content": result.get("content", ""),
                    "tool_calls": result.get("tool_calls", []),
                }

            except Exception as e:
                self._last_llm_error = str(e)
                if attempt < self.max_retries:
                    delay = RETRY_DELAY_SECONDS * (2**attempt) * (1 + random.uniform(-RETRY_JITTER, RETRY_JITTER))
                    if self.on_stream:
                        self.on_stream(
                            f"\n  [{self.name}] LLM error: {e!s:.80}, "
                            f"retrying in {delay:.0f}s ({attempt + 1}/{self.max_retries})...\n"
                        )
                    time.sleep(delay)
                    continue
                if self.on_stream:
                    self.on_stream(f"\n  [{self.name}] LLM error: {self._last_llm_error}\n")
                return None

        return None

    def _execute_tool(self, tool_call: dict[str, Any]) -> str:
        """Execute a single tool call."""
        fn_info = tool_call.get("function", tool_call)
        name = fn_info.get("name", "")
        args_str = fn_info.get("arguments", "{}")

        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {"raw_input": args_str}

        tool = self.registry.get(name)
        if not tool:
            return json.dumps({"error": f"Tool '{name}' not found."})

        try:
            result = tool.call(args, self.context)
            if result.error:
                return json.dumps({"error": result.error})
            if isinstance(result.data, str):
                return result.data
            return json.dumps(result.data, default=str, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {e}"})
