"""
PythonAI Core — Tool Calling Engine (Phase 3)
==============================================
The central LLM + tools loop — PythonAI's 'QueryEngine'.
Upgraded with Claude Code patterns:
- Parallel tool execution (concurrency-aware batching)
- Token budget auto-continuation
- Model fallback on failure
- 3-tier message compaction (micro, auto, reactive)
- Dependency injection for testability
- Immutable config snapshots
"""

from __future__ import annotations

import json
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from .registry import ToolRegistry, get_registry
from .tool import (
    PermissionDecision,
    Tool,
    ToolUseContext,
)

# =======================================
#  Immutable Config Snapshot
# =======================================


@dataclass(frozen=True)
class QueryConfig:
    """Immutable config snapshot captured at query entry."""

    max_tool_rounds: int = 25
    max_budget_tokens: int | None = None
    enable_auto_compact: bool = True
    enable_micro_compact: bool = True
    enable_reactive_compact: bool = True
    enable_token_budget: bool = True
    enable_model_fallback: bool = True
    enable_parallel_tools: bool = True
    model_context_window: int = 128_000
    microcompact_gap_minutes: int = 30
    microcompact_keep_recent: int = 10
    microcompact_trigger_count: int = 25


# =======================================
#  Dependency Injection
# =======================================


@dataclass
class QueryDeps:
    """Injectable dependencies for the engine.
    Enables unit testing with mock implementations.
    """

    call_llm: Callable[..., Any] | None = None
    microcompact: Callable[..., Any] | None = None
    autocompact: Callable[..., Any] | None = None
    reactive_compact: Callable[..., Any] | None = None
    check_token_budget: Callable[..., Any] | None = None


# =======================================
#  Message Types
# =======================================


class Message:
    """A message in the conversation."""

    def __init__(
        self,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
        timestamp: float | None = None,
    ):
        self.role = role  # "system", "user", "assistant", "tool"
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id
        self.name = name
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg

    def to_openai_dict(self) -> dict[str, Any]:
        """OpenAI API format."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


# =======================================
#  Tool Call Parser
# =======================================


def parse_tool_calls(response_text: str) -> list[dict[str, Any]]:
    """Parse tool calls from LLM response text."""
    tool_calls = []

    # Try JSON format first
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            if "name" in data and "arguments" in data:
                tool_calls.append(
                    {
                        "id": f"call_{int(time.time() * 1000)}",
                        "type": "function",
                        "function": {
                            "name": data["name"],
                            "arguments": json.dumps(data["arguments"])
                            if isinstance(data["arguments"], dict)
                            else data["arguments"],
                        },
                    }
                )
                return tool_calls
            if "tool_calls" in data:
                return data["tool_calls"]  # type: ignore[no-any-return]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    tool_calls.append(
                        {
                            "id": f"call_{int(time.time() * 1000)}",
                            "type": "function",
                            "function": {
                                "name": item["name"],
                                "arguments": json.dumps(item.get("arguments", {})),
                            },
                        }
                    )
            return tool_calls
    except (json.JSONDecodeError, TypeError):
        pass

    # Try XML format
    import re

    xml_calls = re.findall(
        r"<(?:tool_call|invoke|use_tool)>"
        r"\s*<(?:tool_name|name)>(.*?)</(?:tool_name|name)>"
        r"\s*<(?:parameters|arguments|input)>(.*?)</(?:parameters|arguments|input)>"
        r"\s*</(?:tool_call|invoke|use_tool)>",
        response_text,
        re.DOTALL,
    )
    for name, args_text in xml_calls:
        try:
            args = json.loads(args_text.strip())
        except json.JSONDecodeError:
            args = {"raw": args_text.strip()}
        tool_calls.append(
            {
                "id": f"call_{int(time.time() * 1000)}",
                "type": "function",
                "function": {"name": name.strip(), "arguments": json.dumps(args)},
            }
        )

    if not tool_calls:
        inline_calls = re.findall(r"(?:Tool|tool):\s*(\w+)\s*\((.+?)\)\s*(?:\n|$)", response_text)
        for name, args_str in inline_calls:
            args = {}
            for kv in re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_str):
                args[kv[0]] = kv[1]
            tool_calls.append(
                {
                    "id": f"call_{int(time.time() * 1000)}",
                    "type": "function",
                    "function": {"name": name.strip(), "arguments": json.dumps(args)},
                }
            )

    return tool_calls


# =======================================
#  Partition Tool Calls by Concurrency
# =======================================


@dataclass
class ToolBatch:
    """A batch of tool calls to execute."""

    is_concurrency_safe: bool
    blocks: list[dict[str, Any]]


def partition_tool_calls(
    tool_calls: list[dict[str, Any]],
    registry: ToolRegistry,
) -> list[ToolBatch]:
    """Partition tool calls into concurrency-safe batches.

    Inspired by Claude Code's partitionToolCalls().
    Read-only tools run in parallel batches; write tools run serially.
    """
    batches: list[ToolBatch] = []

    for tc in tool_calls:
        fn_info = tc.get("function", tc)
        name = fn_info.get("name", "")

        tool = registry.get(name)
        is_safe = bool(tool and tool.is_concurrency_safe())

        if is_safe and batches and batches[-1].is_concurrency_safe:
            batches[-1].blocks.append(tc)
        else:
            batches.append(ToolBatch(is_concurrency_safe=is_safe, blocks=[tc]))

    return batches


# =======================================
#  Tool Calling Engine (Phase 3)
# =======================================


class ToolCallingEngine:
    """The central LLM + tools loop — Phase 3 upgraded.

    Key improvements over Phase 1:
    - Parallel tool execution (read-only tools run concurrently)
    - Token budget auto-continuation
    - Model fallback to next provider on failure
    - 3-tier message compaction integration
    - Dependency injection for testability
    - Immutable config snapshots
    """

    def __init__(
        self,
        provider: str = "auto",
        model: str = "",
        registry: ToolRegistry | None = None,
        max_tool_rounds: int = 25,
        on_stream: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[str, Any], None] | None = None,
        deps: QueryDeps | None = None,
        config: QueryConfig | None = None,
    ):
        self.provider = provider
        self.model = model
        self.registry = registry or get_registry()
        self.on_stream = on_stream
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result

        # Dependencies + Config
        self.deps = deps or QueryDeps()
        self.max_tool_rounds = max_tool_rounds
        self.config = config or QueryConfig(max_tool_rounds=max_tool_rounds)

        # Conversation
        self.messages: list[Message] = []
        self.context = ToolUseContext()

        # Token budget tracker
        self._budget_tracker: Any = None
        self._setup_budget_tracker()

        # Compaction stats
        self.compact_stats: dict[str, Any] = {
            "micro_compactions": 0,
            "auto_compactions": 0,
            "reactive_compactions": 0,
            "total_tokens_saved": 0,
        }

        # Model fallback chain
        self._fallback_providers: list[str] = []

        # Statistics
        self.stats: dict[str, Any] = {
            "total_rounds": 0,
            "total_tool_calls": 0,
            "total_tokens": 0,
            "start_time": 0,
            "end_time": 0,
            "total_parallel_batches": 0,
            "model_fallbacks": 0,
        }

    def _setup_budget_tracker(self) -> None:
        """Initialize budget tracker if token budget is enabled."""
        if self.config.enable_token_budget and self.deps.check_token_budget:
            from .engine.token_budget import BudgetTracker

            self._budget_tracker = BudgetTracker()
        elif self.config.enable_token_budget:
            from .engine.token_budget import BudgetTracker

            self._budget_tracker = BudgetTracker()

    # == Provider Methods =====================================

    def _call_llm(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Call LLM with model fallback support."""
        # Use injected deps first
        if self.deps.call_llm:
            return self.deps.call_llm(messages, tools)  # type: ignore[no-any-return]

        try:
            from .providers import ProfileManager, ProviderRouter, get_provider_api

            router = ProviderRouter()

            # Load profile
            profile = ProfileManager().load()
            routed_provider = self.provider
            routed_model = self.model
            if profile:
                routed_provider = profile.provider
                routed_model = profile.model or routed_model

            # Route
            route = router.route(
                provider=routed_provider,
                model=routed_model,
                task="coding",
                require_function_calling=bool(tools),
            )

            if route.error:
                # Try fallback chain
                return self._call_with_fallback(messages, tools, router)

            # Build messages for API
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
                    formatted.append({"role": msg["role"], "content": msg["content"]})

            if system_content:
                tool_text = self._format_tools_for_prompt(tools)
                formatted.insert(
                    0,
                    {
                        "role": "system",
                        "content": system_content + "\n\n" + tool_text,
                    },
                )

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
                # Fallback
                return self._call_with_fallback(messages, tools, router)

            # Track tokens
            usage = result.get("usage", {})
            self.stats["total_tokens"] += usage.get("total_tokens", 0)

            return {
                "content": result.get("content", ""),
                "tool_calls": result.get("tool_calls", []),
                "model": route.model,
                "provider": route.provider,
            }

        except ImportError:
            from src.utils.llm import generate_with_provider

            return self._call_llm_legacy(messages, tools, generate_with_provider)

    def _call_with_fallback(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], router: Any
    ) -> dict[str, Any]:
        """Try fallback providers when primary fails."""
        if not self.config.enable_model_fallback:
            from src.utils.llm import generate_with_provider

            return self._call_llm_legacy(messages, tools, generate_with_provider)

        # Build fallback chain
        if not self._fallback_providers:
            available = router.get_available_providers()
            self._fallback_providers = [
                p.id for p in available if p.id != self.provider and not p.is_local and p.requires_key
            ]
            # Add local as last resort
            self._fallback_providers.append("ollama")

        # Try each fallback
        for fb_provider in self._fallback_providers:
            route = router.route(provider=fb_provider)
            if route.error:
                continue

            try:
                from .providers import get_provider_api

                api_fn = get_provider_api(fb_provider)

                formatted = []
                for msg in messages:
                    if msg["role"] == "system":
                        continue
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
                        formatted.append({"role": msg["role"], "content": msg["content"]})

                result = api_fn(
                    messages=formatted,
                    model=route.model,
                    base_url=route.base_url,
                    api_key=route.api_key or "",
                    temperature=0.3,
                    max_tokens=4096,
                    tools=tools if tools else None,
                )

                if not result.get("error"):
                    self.stats["model_fallbacks"] += 1
                    self.stats["total_tokens"] += result.get("usage", {}).get("total_tokens", 0)
                    return {
                        "content": result.get("content", ""),
                        "tool_calls": result.get("tool_calls", []),
                        "model": route.model,
                        "provider": fb_provider,
                        "fallback": True,
                    }
            except Exception:
                continue

        # All fallbacks failed
        from src.utils.llm import generate_with_provider

        return self._call_llm_legacy(messages, tools, generate_with_provider)

    def _call_llm_legacy(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], generate_fn: Any
    ) -> dict[str, Any]:
        """Fallback using legacy system."""
        system_prompt = self._build_system_prompt(tools)

        prompt_parts = []
        for msg in messages:
            if msg["role"] == "system":
                continue
            if msg["role"] == "user":
                prompt_parts.append(f"User: {msg['content']}")
            elif msg["role"] == "assistant":
                prompt_parts.append(f"Assistant: {msg['content']}")
            elif msg["role"] == "tool":
                prompt_parts.append(f"Tool Result ({msg.get('name', 'unknown')}): {msg['content']}")

        prompt = "\n\n".join(prompt_parts)
        full_prompt = (
            f"{system_prompt}\n\n"
            f"Available tools:\n{self._format_tools_for_prompt(tools)}\n\n"
            f"Conversation:\n{prompt}\n\n"
            f"Assistant:"
        )

        response = generate_fn(full_prompt, provider=self.provider, system_prompt=system_prompt)
        return {"content": response, "tool_calls": []}

    # == System Prompt ========================================

    def _build_system_prompt(self, tools: list[dict[str, Any]]) -> str:
        return f"""You are PythonAI — an elite AI coding assistant with access to powerful tools.

Available tools:
{self._format_tools_for_prompt(tools)}

To use a tool, respond with JSON:
{{"name": "tool_name", "arguments": {{"param1": "value1"}}}}

After receiving tool results, use them to continue your response.
Think step by step about which tools to use and in what order."""

    def _format_tools_for_prompt(self, tools: list[dict[str, Any]]) -> str:
        parts = []
        for tool in tools:
            fn = tool.get("function", tool)
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            props = params.get("properties", {})
            param_lines = []
            for pname, pinfo in props.items():
                required = pname in params.get("required", [])
                req_mark = " (required)" if required else ""
                param_lines.append(
                    f"    {pname}: {pinfo.get('type', 'any')}{req_mark} - {pinfo.get('description', '')}"
                )
            parts.append(f"  - {name}: {desc}")
            if param_lines:
                parts.append("    Parameters:")
                parts.extend(param_lines)
        return "\n".join(parts)

    # == Tool Execution (Parallel + Serial) ===================

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

        validation = tool.validate_input(args, self.context)
        if not validation.success:
            return json.dumps({"error": f"Validation failed: {validation.message}"})

        permission = tool.check_permissions(args, self.context)
        if permission.behavior in (PermissionDecision.DENY, PermissionDecision.ALWAYS_DENY):
            return json.dumps({"error": f"Permission denied: {permission.message}"})

        if self.on_tool_call:
            self.on_tool_call(name, args)

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
            return json.dumps({"error": f"Tool execution failed: {e}", "traceback": tb[-500:]})

    def _execute_batch(self, batch: ToolBatch) -> list[dict[str, Any]]:
        """Execute a batch of tool calls (parallel if safe)."""
        if batch.is_concurrency_safe and self.config.enable_parallel_tools and len(batch.blocks) > 1:
            return self._execute_parallel_batch(batch.blocks)
        return self._execute_serial_batch(batch.blocks)

    def _execute_parallel_batch(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute read-only tools in parallel."""
        self.stats["total_parallel_batches"] += 1
        results_map: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(len(blocks), 10)) as executor:
            future_map: dict[Any, int] = {}
            for i, tc in enumerate(blocks):
                future = executor.submit(self._execute_tool, tc)
                future_map[future] = i

            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    result_content = future.result(timeout=120)
                except Exception as e:
                    result_content = json.dumps({"error": f"Parallel tool execution failed: {e}"})
                fn_info = blocks[idx].get("function", blocks[idx])
                results_map[idx] = {
                    "tool_call_id": blocks[idx].get("id", "call_unknown"),
                    "name": fn_info.get("name", "unknown"),
                    "content": result_content,
                }

        return [results_map[i] for i in sorted(results_map.keys())]

    def _execute_serial_batch(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute tools serially (for write tools)."""
        results = []
        for tc in blocks:
            result_content = self._execute_tool(tc)
            fn_info = tc.get("function", tc)
            results.append(
                {
                    "tool_call_id": tc.get("id", "call_unknown"),
                    "name": fn_info.get("name", "unknown"),
                    "content": result_content,
                }
            )
        return results

    # == Compaction Integration ===============================

    def _apply_micro_compact(self) -> dict[str, Any] | None:
        """Apply micro-compaction before API call."""
        if not self.config.enable_micro_compact:
            return None
        try:
            msg_dicts = [m.to_dict() for m in self.messages]
            from .compact.micro_compact import microcompact_messages

            result = microcompact_messages(
                msg_dicts,
                time_gap_minutes=self.config.microcompact_gap_minutes,
                count_keep_recent=self.config.microcompact_keep_recent,
                count_trigger=self.config.microcompact_trigger_count,
            )
            if result.get("compacted"):
                self.compact_stats["micro_compactions"] += 1
                self.compact_stats["total_tokens_saved"] += result.get("tokens_saved", 0)
                # Rebuild messages from compacted dicts
                self.messages = []
                for d in result["messages"]:
                    msg = Message(
                        role=d["role"],
                        content=d["content"],
                        tool_call_id=d.get("tool_call_id"),
                        name=d.get("name"),
                        timestamp=d.get("timestamp"),
                    )
                    if d.get("tool_calls"):
                        msg.tool_calls = d["tool_calls"]
                    self.messages.append(msg)
                return result  # type: ignore[no-any-return]
        except ImportError:
            pass
        return None

    def _apply_auto_compact(self) -> dict[str, Any] | None:
        """Apply auto-compaction if token count exceeds threshold."""
        if not self.config.enable_auto_compact:
            return None
        try:
            msg_dicts = [m.to_dict() for m in self.messages]
            from .compact.auto_compact import _simple_compact, auto_compact_if_needed

            result = auto_compact_if_needed(
                msg_dicts,
                model_context_window=self.config.model_context_window,
                compact_fn=_simple_compact,
            )
            if result.get("was_compacted"):
                self.compact_stats["auto_compactions"] += 1
                cr = result.get("compacted_result", {})
                self.compact_stats["total_tokens_saved"] += cr.get("tokens_saved", 0)
                self.messages = []
                for d in result["messages"]:
                    msg = Message(
                        role=d["role"],
                        content=d["content"],
                        tool_call_id=d.get("tool_call_id"),
                        name=d.get("name"),
                        timestamp=d.get("timestamp"),
                    )
                    if d.get("tool_calls"):
                        msg.tool_calls = d["tool_calls"]
                    self.messages.append(msg)
                return result  # type: ignore[no-any-return]
        except ImportError:
            pass
        return None

    def _check_reactive_compact(self, response: dict[str, Any]) -> dict[str, Any] | None:
        """Check if response has PTL error and try reactive compact."""
        if not self.config.enable_reactive_compact:
            return None
        try:
            msg_dicts = [m.to_dict() for m in self.messages]
            from .compact.reactive_compact import is_prompt_too_long_error, reactive_compact_if_needed

            if not is_prompt_too_long_error(response):
                return None
            from .compact.auto_compact import _simple_compact

            result = reactive_compact_if_needed(
                response,
                msg_dicts,
                compact_fn=_simple_compact,
            )
            if result.get("should_retry") and result.get("compacted_messages"):
                self.compact_stats["reactive_compactions"] += 1
                self.messages = []
                for d in result["compacted_messages"]:
                    msg = Message(
                        role=d["role"],
                        content=d["content"],
                        tool_call_id=d.get("tool_call_id"),
                        name=d.get("name"),
                        timestamp=d.get("timestamp"),
                    )
                    if d.get("tool_calls"):
                        msg.tool_calls = d["tool_calls"]
                    self.messages.append(msg)
                return result  # type: ignore[no-any-return]
        except ImportError:
            pass
        return None

    # == Main Loop ============================================

    def run(
        self, user_input: str, system_prompt: str | None = None, tools: list[Tool] | None = None, stream: bool = False
    ) -> str:
        """
        Run the tool-calling loop with all Phase 3 upgrades.

        Args:
            user_input: The user's message.
            system_prompt: Optional override.
            tools: Optional tool list (default: all registered).
            stream: Whether to stream.

        Returns:
            The final assistant response.
        """
        self.stats["start_time"] = time.time()
        self.stats["total_rounds"] = 0

        if tools is None:
            tools = self.registry.list_all()

        tool_defs = [t.to_openai_tool() for t in tools]

        # Add user message
        self.messages.append(Message("user", user_input))

        # Token budget tracker
        if self._budget_tracker:
            self._budget_tracker.reset()

        # Track reactive compact retries
        reactive_retry_count = 0
        max_reactive_retries = 2

        # == Tool-calling loop =================================
        for round_num in range(self.config.max_tool_rounds):
            self.stats["total_rounds"] = round_num + 1

            # Step 1: Micro-compaction (pre-request)
            self._apply_micro_compact()

            # Step 2: Auto-compaction (pre-request)
            self._apply_auto_compact()

            # Build message list
            msg_dicts = [m.to_openai_dict() for m in self.messages]

            # Call LLM
            response = self._call_llm(msg_dicts, tool_defs)

            # Step 3: Reactive compaction (on PTL error)
            reactive_result = self._check_reactive_compact(response)
            if reactive_result and reactive_result.get("should_retry"):
                reactive_retry_count += 1
                if reactive_retry_count < max_reactive_retries:
                    continue  # Retry with compacted messages
                else:
                    break  # Max retries reached

            response_text = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            # Parse tool calls from response
            if not tool_calls and response_text:
                parsed = parse_tool_calls(response_text)
                if parsed:
                    tool_calls = parsed
                    response_text = ""

            # Stream text
            if response_text and self.on_stream:
                self.on_stream(response_text)

            # If no tool calls, we're done
            if not tool_calls:
                self.messages.append(Message("assistant", response_text))
                break

            # == Execute tool calls with concurrency batching ==
            self.messages.append(Message("assistant", response_text or "", tool_calls=tool_calls))

            # Partition into batches
            batches = partition_tool_calls(tool_calls, self.registry)

            # Execute each batch
            all_results = []
            for batch in batches:
                batch_results = self._execute_batch(batch)
                all_results.extend(batch_results)

            # Add tool results to messages
            for tr in all_results:
                self.messages.append(
                    Message(
                        role="tool",
                        content=tr["content"],
                        tool_call_id=tr["tool_call_id"],
                        name=tr["name"],
                    )
                )

            # == Token budget check (auto-continuation) ========
            if self._budget_tracker and round_num > 0:
                try:
                    from .engine.token_budget import check_token_budget

                    decision = check_token_budget(
                        self._budget_tracker,
                        None,  # no agent_id
                        50_000,  # default budget
                        self.stats["total_tokens"],
                    )
                    if decision.action == "continue":
                        # Inject continuation nudge
                        self.messages.append(Message("user", decision.nudge_message))
                        continue
                except ImportError:
                    pass

        self.stats["end_time"] = time.time()

        # Return the final assistant response
        assistant_messages = [m for m in self.messages if m.role == "assistant"]
        return assistant_messages[-1].content if assistant_messages else response_text

    def stream_run(self, user_input: str, **kwargs: Any) -> str:
        return self.run(user_input, stream=True, **kwargs)

    def reset(self) -> None:
        self.messages = []
        self._fallback_providers = []
        if self._budget_tracker:
            self._budget_tracker.reset()
        self.stats = {k: 0 if isinstance(v, int) else v for k, v in self.stats.items()}

    def get_stats_report(self) -> dict[str, Any]:
        elapsed = self.stats.get("end_time", time.time()) - self.stats.get("start_time", time.time())
        return {
            "total_rounds": self.stats["total_rounds"],
            "total_tool_calls": self.stats["total_tool_calls"],
            "total_parallel_batches": self.stats["total_parallel_batches"],
            "total_tokens": self.stats["total_tokens"],
            "model_fallbacks": self.stats["model_fallbacks"],
            "elapsed_seconds": round(elapsed, 2),
            "messages_count": len(self.messages),
            "compaction": {
                "micro_compactions": self.compact_stats["micro_compactions"],
                "auto_compactions": self.compact_stats["auto_compactions"],
                "reactive_compactions": self.compact_stats["reactive_compactions"],
                "total_tokens_saved": self.compact_stats["total_tokens_saved"],
            },
        }
