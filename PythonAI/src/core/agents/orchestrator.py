"""
PythonAI Agentic System — AgentOrchestrator
============================================
Master orchestrator that plans complex tasks, delegates sub-tasks
to specialized SubAgents, and synthesizes results into a final answer.

Flow:
  1. Plan — Decompose user request into sub-tasks with dependencies
  2. Delegate — Assign sub-tasks to appropriate SubAgents
  3. Execute — Run agents (parallel or sequential based on dependencies)
  4. Synthesize — Combine results into final coherent response
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..registry import ToolRegistry, get_registry
from .sub_agent import SubAgent, SubAgentResult
from .swarm import AgentSwarm

logger = logging.getLogger("pythonai.orchestrator")

# MCP auto-connect is attempted before planning
# Only imported when needed (lazy import)


@dataclass
class PlanStep:
    """A single step in the orchestration plan."""

    id: str
    agent_name: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    priority: int = 5  # Lower = higher priority
    status: str = "pending"  # pending, running, done, failed


class AgentOrchestrator:
    """Master orchestrator that plans and coordinates sub-agents.

    Takes a complex user request, breaks it down, delegates to
    specialized sub-agents, and synthesizes the final response.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        call_llm_fn: Callable[..., Any] | None = None,
        on_stream: Callable[[str], None] | None = None,
        on_plan: Callable[[list[PlanStep]], None] | None = None,
        max_concurrent: int = 4,
        verbose: bool = False,
    ):
        self.registry = registry or get_registry()
        self.call_llm_fn = call_llm_fn
        self.on_stream = on_stream
        self.on_plan = on_plan
        self.max_concurrent = max_concurrent
        self.verbose = verbose

        # MCP client (created by _auto_connect_mcp, closed by cleanup)
        self._mcp_client: Any | None = None

        # Create default sub-agents
        self._swarm = AgentSwarm(
            max_concurrent=max_concurrent,
            on_agent_start=self._on_agent_start,
            on_agent_complete=self._on_agent_complete,
        )
        self._init_default_agents()

        # Plan
        self.plan: list[PlanStep] = []
        self.results: dict[str, SubAgentResult] = {}

    def _init_default_agents(self) -> None:
        """Initialize the default set of sub-agents."""
        agents = [
            SubAgent.coding_agent(
                registry=self.registry,
                call_llm_fn=self.call_llm_fn,
                on_stream=self.on_stream,
            ),
            SubAgent.research_agent(
                registry=self.registry,
                call_llm_fn=self.call_llm_fn,
                on_stream=self.on_stream,
            ),
            SubAgent.review_agent(
                registry=self.registry,
                call_llm_fn=self.call_llm_fn,
                on_stream=self.on_stream,
            ),
        ]

        # Add MCP agent if MCP tools are registered
        if self.registry.list_mcp():
            agents.append(
                SubAgent.mcp_agent(
                    registry=self.registry,
                    call_llm_fn=self.call_llm_fn,
                    on_stream=self.on_stream,
                )
            )

        for agent in agents:
            self._swarm.add_agent(agent)

    def register_agent(self, agent: SubAgent) -> None:
        """Register a custom sub-agent."""
        self._swarm.add_agent(agent)

    # ── Callbacks ────────────────────────────────────────────

    def _on_agent_start(self, agent_name: str) -> None:
        for step in self.plan:
            if step.agent_name == agent_name:
                step.status = "running"
        if self.on_stream is not None:
            self.on_stream(f"\n[Orchestrator] Starting agent: {agent_name}\n")

    def _on_agent_complete(self, agent_name: str, result: SubAgentResult) -> None:
        for step in self.plan:
            if step.agent_name == agent_name:
                step.status = "done" if result.success else "failed"
        if self.on_stream is not None:
            status = "done" if result.success else "failed"
            self.on_stream(
                f"\n[Orchestrator] Agent '{agent_name}' {status}: "
                f"{result.rounds}r/{result.tool_calls_used}t "
                f"in {result.elapsed:.1f}s\n"
            )

    # ── Planning ─────────────────────────────────────────────

    def _call_planning_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str | None:
        """Call the LLM for planning or synthesis tasks (no tools)."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.call_llm_fn is not None:
            try:
                result = self.call_llm_fn(messages, [])
                if result is not None:
                    return result.get("content", "")  # type: ignore[no-any-return]
                return None
            except Exception as e:
                logger.debug(f"Planning LLM call via injected fn failed: {e}")
                return None

        try:
            from ..providers import ProfileManager, ProviderRouter, get_provider_api

            router = ProviderRouter()
            profile = ProfileManager().load()
            provider = profile.provider if profile else "auto"
            model = profile.model if profile else ""

            route = router.route(
                provider=provider,
                model=model,
                task="reasoning",
                require_function_calling=False,
            )

            if route.error:
                # Try fallback to first available
                available = router.get_available_providers()
                if not available:
                    logger.debug(f"Planning LLM call failed: {route.error}")
                    return None
                for p in available:
                    r = router.route(provider=p.id)
                    if not r.error:
                        route = r
                        break
                else:
                    return None

            api_fn = get_provider_api(route.provider)
            result = api_fn(
                messages=messages,
                model=route.model,
                base_url=route.base_url,
                api_key=route.api_key or "",
                temperature=0.3,
                max_tokens=max_tokens,
                tools=None,
            )

            if result.get("error"):
                logger.debug(f"Planning LLM API error: {result['error']}")
                return None

            # Mypy: api_fn returns Any, cast to str for return type
            return result.get("content", "")  # type: ignore[no-any-return]

        except Exception as e:
            logger.debug(f"Planning LLM exception: {e}")
            return None

    def plan_task(self, user_request: str) -> list[PlanStep]:
        """Decompose a user request into a plan of sub-tasks."""
        self.plan = []

        # 1. Try LLM-based planning
        llm_steps = self._plan_task_llm(user_request)
        if llm_steps is not None:
            steps = llm_steps
        else:
            # 2. Fallback to keyword-based planning
            if self.on_stream is not None:
                self.on_stream("[Orchestrator] LLM planning unavailable/failed. Falling back to keyword matching.\n")
            steps = self._plan_task_keyword_fallback(user_request)

        self.plan = steps

        if self.on_plan is not None:
            self.on_plan(steps)

        if self.verbose or self.on_stream is not None:
            stream = self.on_stream
            if stream is not None:
                stream("\n[Orchestrator] Plan:\n")
                for s in steps:
                    deps = f" (after: {', '.join(s.depends_on)})" if s.depends_on else ""
                    stream(f"  {s.id}: [{s.agent_name}] {s.task[:60]}...{deps}\n")
                stream("\n")

        return steps

    def _plan_task_llm(self, user_request: str) -> list[PlanStep] | None:
        """Use an LLM to decompose the request into a JSON array of PlanSteps."""
        if self.on_stream is not None:
            self.on_stream("  [LLM] Planning...\n")

        agents_info = [f"- {agent_name} ({agent.role})" for agent_name, agent in self._swarm.agents.items()]

        mcp_tools = [f"{t.name}: {t.description[:100]}" for t in self.registry.list_mcp()]
        mcp_info = "\nAvailable MCP Tools:\n" + "\n".join(mcp_tools) if mcp_tools else ""

        system_prompt = f"""You are an elite orchestrator AI. Your job is to break down a complex user request into a sequence of sub-tasks assigned to specialized agents.

Available Agents:
{chr(10).join(agents_info)}
{mcp_info}

Rules:
1. Decompose the task into discrete, actionable steps.
2. Assign each step to exactly ONE of the available agents.
3. Identify dependencies (a step can depend on the IDs of previous steps).
4. Output ONLY valid JSON containing a list of objects. No markdown formatting blocks around the JSON.

Expected JSON schema:
[
  {{
    "id": "step_0",
    "agent_name": "coder",
    "task": "Specific instructions for the agent",
    "depends_on": [],
    "priority": 1
  }}
]
"""
        response_text = self._call_planning_llm(system_prompt, user_request, max_tokens=1024)
        if not response_text:
            return None

        try:
            # Clean up markdown formatting if the LLM ignored instructions
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            parsed = json.loads(response_text)
            if not isinstance(parsed, list):
                logger.debug("LLM plan response was not a list")
                return None

            steps = []
            for item in parsed:
                if not isinstance(item, dict) or "id" not in item or "agent_name" not in item or "task" not in item:
                    logger.debug(f"Invalid plan step item: {item}")
                    return None

                agent_name = item["agent_name"]
                if agent_name not in self._swarm.agents:
                    # Map back to a known agent or fallback
                    agent_name = "coder" if "coder" in self._swarm.agents else list(self._swarm.agents.keys())[0]

                steps.append(
                    PlanStep(
                        id=item["id"],
                        agent_name=agent_name,
                        task=item["task"],
                        depends_on=item.get("depends_on", []),
                        priority=item.get("priority", 5),
                    )
                )

            return steps

        except json.JSONDecodeError as e:
            logger.debug(f"LLM plan JSON decode error: {e}\nResponse was: {response_text}")
            return None
        except Exception as e:
            logger.debug(f"LLM plan parsing exception: {e}")
            return None

    def _plan_task_keyword_fallback(self, user_request: str) -> list[PlanStep]:
        """Decompose a user request using simple keyword matching."""
        request_lower = user_request.lower()

        steps: list[PlanStep] = []
        step_id = 0

        # Check if research is needed (reading files, searching)
        needs_research = any(
            w in request_lower
            for w in [
                "find",
                "search",
                "read",
                "lookup",
                "check",
                "what",
                "list",
                "show",
                "where",
                "examine",
                "review existing",
            ]
        )

        # Check if coding is needed
        needs_coding = any(
            w in request_lower
            for w in [
                "write",
                "create",
                "implement",
                "build",
                "code",
                "fix",
                "add",
                "update",
                "modify",
                "change",
                "edit",
                "refactor",
                "make",
                "generate",
                "develop",
            ]
        )

        # Check if review is needed (complex tasks)
        needs_review = needs_coding and any(
            w in request_lower
            for w in [
                "complex",
                "sophisticated",
                "production",
                "secure",
                "review",
                "validate",
                "verify",
            ]
        )

        # Check if MCP is needed
        needs_mcp = any(
            w in request_lower
            for w in [
                "mcp",
                "filesystem",
                "database",
                "server",
                "external",
            ]
        ) and bool(self.registry.list_mcp())

        # Build the plan
        if needs_research:
            steps.append(
                PlanStep(
                    id=f"step_{step_id}",
                    agent_name="researcher",
                    task=f"Research: {user_request}",
                    depends_on=[],
                    priority=1,
                )
            )
            step_id += 1

        if needs_coding:
            deps = ["step_0"] if needs_research else []
            steps.append(
                PlanStep(
                    id=f"step_{step_id}",
                    agent_name="coder",
                    task=f"Implement: {user_request}",
                    depends_on=deps,
                    priority=2,
                )
            )
            step_id += 1

        if needs_mcp:
            deps = []
            if needs_research:
                deps.append("step_0")
            steps.append(
                PlanStep(
                    id=f"step_{step_id}",
                    agent_name="mcp-worker",
                    task=f"MCP: {user_request}",
                    depends_on=deps,
                    priority=3,
                )
            )
            step_id += 1

        if needs_review:
            deps = [f"step_{i}" for i in range(step_id)]
            steps.append(
                PlanStep(
                    id=f"step_{step_id}",
                    agent_name="reviewer",
                    task=f"Review: {user_request}",
                    depends_on=deps,
                    priority=4,
                )
            )
            step_id += 1

        # Fallback: use coder agent as default
        if not steps:
            steps.append(
                PlanStep(
                    id="step_0",
                    agent_name="coder",
                    task=user_request,
                    depends_on=[],
                    priority=5,
                )
            )

        return steps

    # ── MCP Auto-Connect ────────────────────────────────────────

    def _auto_connect_mcp(self) -> int:
        """Discover and connect to configured MCP servers.

        Loads MCP config files (.mcp.json, user config),
        connects to all configured servers via JSON-RPC,
        and registers their tools in the shared registry.

        Stores the MCPClient reference for cleanup via close().

        Returns:
            Number of MCP tools registered.
        """
        if self.on_stream is not None:
            self.on_stream("[Orchestrator] Discovering MCP servers...\n")

        # 1. Close any previous connections (before import, so it runs even if MCP is unavailable)
        self.cleanup()

        try:
            from src.core.mcp import MCPClient, MCPConfigManager

            # 2. Find configured servers
            config_mgr = MCPConfigManager()
            configured = config_mgr.get_servers()

            if not configured:
                return 0

            if self.on_stream is not None:
                names = ", ".join(configured.keys())
                self.on_stream(f"  Configs found: {len(configured)} ({names})\n")

            # 3. Create client and connect to each server
            self._mcp_client = MCPClient()
            connections: dict[str, Any] = {}
            for name, config in configured.items():
                conn = self._mcp_client.connect(config, name=name)
                connections[name] = conn

            # 4. Register tools from connected servers
            connected_count = 0
            tool_count = 0

            for name, conn in connections.items():
                if conn.state.name == "CONNECTED":
                    count = self.registry.register_mcp_server(conn)
                    connected_count += 1
                    tool_count += count
                    if self.on_stream is not None:
                        self.on_stream(f"  [OK] {name}: {len(conn.tools)} tools, {len(conn.resources)} resources\n")
                else:
                    if self.on_stream is not None:
                        self.on_stream(f"  [--] {name}: {conn.error or 'failed'}\n")

            if connected_count and self.on_stream is not None:
                self.on_stream(
                    f"  Total: {connected_count}/{len(connections)} connected, {tool_count} tools registered\n"
                )

            # 5. Re-init default agents so MCP agent is available
            if tool_count:
                self._swarm = AgentSwarm(
                    max_concurrent=self.max_concurrent,
                    on_agent_start=self._on_agent_start,
                    on_agent_complete=self._on_agent_complete,
                )
                self._init_default_agents()

            return tool_count

        except Exception as e:
            logger.debug(f"MCP auto-connect failed: {e}\n{traceback.format_exc()}")
            if self.on_stream is not None:
                self.on_stream(f"  [MCP] Auto-connect skipped: {e}\n")
            return 0

    # ── Context Manager ───────────────────────────────────────────

    def __enter__(self) -> AgentOrchestrator:
        """Enter context manager: return self for use in `with` blocks.

        Usage:
            with AgentOrchestrator(...) as orch:
                result = orch.run("task")
            # MCP connections are automatically cleaned up on exit
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exit context manager: clean up MCP connections.

        Called when exiting a `with` block, even if an exception occurred.
        Ensures MCP server processes are shut down and file handles released.
        """
        self.cleanup()

    # ── Cleanup ───────────────────────────────────────────────

    def cleanup(self) -> None:
        """Close all MCP connections and release resources.

        Call this after orchestration completes to cleanly shut down
        MCP server processes (npx, etc.) and release file handles.
        Safe to call multiple times and when no MCP client exists.
        """
        if self._mcp_client is not None:
            try:
                self._mcp_client.close_all()
                if self.on_stream is not None:
                    self.on_stream("[Orchestrator] MCP connections closed\n")
            except Exception as e:
                logger.debug(f"MCP cleanup error: {e}")
            finally:
                self._mcp_client = None

    def __del__(self) -> None:
        """Destructor: ensure MCP connections are cleaned up."""
        self.cleanup()

    # ── Execution ────────────────────────────────────────────

    def run(self, user_request: str) -> str:
        """Run the full orchestration pipeline.

        Automatically discovers and connects MCP servers before
        planning, so sub-agents can use filesystem and database tools.

        Args:
            user_request: The user's complex request.

        Returns:
            Synthesized final response.
        """
        start_time = time.time()

        # Phase 0: Auto-connect MCP servers
        if self.on_stream is not None:
            self.on_stream("\n[Orchestrator] Agentic Mode (Phase 6)\n")
        mcp_tools = self._auto_connect_mcp()

        if self.on_stream is not None:
            self.on_stream(f"  Tools: {self.registry.total_count} registered ({mcp_tools} MCP)\n")

        # Phase 1: Plan
        if self.on_stream is not None:
            self.on_stream("\n[Orchestrator] Planning...\n")

        self.plan_task(user_request)

        # Phase 2: Execute with dependency ordering
        if self.on_stream is not None:
            self.on_stream("[Orchestrator] Executing...\n")

        # Group by dependency level
        executed: set[str] = set()
        pending = {s.id: s for s in self.plan}

        round_num = 0
        while pending and round_num < 10:
            round_num += 1

            # Find steps whose dependencies are met
            ready = [s for s in pending.values() if all(dep in executed for dep in s.depends_on)]

            if not ready:
                break  # Circular dependency or all blocked

            # Prepare tasks
            tasks: dict[str, str] = {}
            contexts: dict[str, str | None] = {}

            for step in ready:
                tasks[step.agent_name] = step.task

                # Build context from completed dependencies
                context_parts = []
                for dep_id in step.depends_on:
                    dep_step = next((s for s in self.plan if s.id == dep_id), None)
                    if dep_step and dep_step.agent_name in self.results:
                        r = self.results[dep_step.agent_name]
                        if r.success:
                            context_parts.append(f"[{dep_step.agent_name} output]:\n{r.output[:1500]}")
                contexts[step.agent_name] = "\n\n".join(context_parts) if context_parts else None

            # Execute ready steps
            step_results = self._swarm.run_all(tasks, contexts)
            self.results.update(step_results)

            # Mark as executed
            for step in ready:
                executed.add(step.id)
                del pending[step.id]

        # Phase 3: Synthesize
        if self.on_stream is not None:
            self.on_stream("[Orchestrator] Synthesizing results...\n")

        synthesis = self._synthesize(user_request)

        elapsed = time.time() - start_time

        if self.on_stream is not None:
            self.on_stream(
                f"\n[Orchestrator] Complete: {len(self.results)} agents, "
                f"{sum(r.tool_calls_used for r in self.results.values())} tools, "
                f"{elapsed:.1f}s\n"
            )

        # Phase 4: Cleanup MCP connections
        self.cleanup()

        return synthesis

    # ── Synthesis ────────────────────────────────────────────

    def _synthesize(self, user_request: str) -> str:
        """Combine all agent results into a coherent response."""
        successful = {name: r for name, r in self.results.items() if r.success and r.output}

        if not successful:
            return "[Orchestrator] All agents failed. See errors above."

        # 1. Try LLM-based synthesis
        llm_synthesis = self._synthesize_llm(user_request, successful)
        if llm_synthesis is not None:
            return llm_synthesis

        # 2. Fallback to concatenation
        if self.on_stream is not None:
            self.on_stream("  [Orchestrator] LLM synthesis unavailable/failed. Falling back to concatenation.\n")
        return self._synthesize_concat_fallback(user_request, successful)

    def _synthesize_llm(self, user_request: str, successful: dict[str, SubAgentResult]) -> str | None:
        """Use LLM to synthesize agent results into a cohesive final answer."""
        if self.on_stream is not None:
            self.on_stream("  [LLM] Synthesizing...\n")

        system_prompt = """You are an elite orchestrator AI. You have delegated a complex user request to several specialized sub-agents.
Your task is to synthesize their individual outputs into a single, cohesive, and comprehensive final response for the user.

Rules:
1. Address the user's original request directly.
2. Combine the findings seamlessly. Do not just list what each agent did, but synthesize the information.
3. Keep it clear, professional, and well-structured.
"""

        agent_outputs = []
        for agent_name, result in successful.items():
            # Truncate overly long outputs to prevent blowing up the context window
            out = result.output[:3000] + ("..." if len(result.output) > 3000 else "")
            agent_outputs.append(f"--- Agent: {agent_name} ({result.role}) ---\n{out}\n")

        user_prompt = f"""User Request: {user_request}

Agent Outputs:
{"".join(agent_outputs)}

Provide the final synthesized response:"""

        # synthesis might need more tokens
        response_text = self._call_planning_llm(system_prompt, user_prompt, max_tokens=2048)
        if not response_text:
            return None

        # Add summary footer
        footer = (
            f"\n\n---\n*Orchestrated across {len(successful)} agents "
            f"({sum(r.tool_calls_used for r in successful.values())} total tool calls)*"
        )
        return response_text.strip() + footer

    def _synthesize_concat_fallback(self, user_request: str, successful: dict[str, SubAgentResult]) -> str:
        """Combine agent results using simple concatenation."""
        # Simple concatenation with headers
        parts = [f"# Results for: {user_request}", ""]

        # Priority ordering: researcher -> coder -> mcp -> reviewer
        priority = {"researcher": 0, "coder": 1, "mcp-worker": 2, "reviewer": 3}
        ordered = sorted(
            successful.items(),
            key=lambda x: priority.get(x[0], 99),
        )

        for agent_name, result in ordered:
            if result.output:
                role_label = agent_name.replace("-", " ").title()
                parts.append(f"## {role_label}")
                parts.append(result.output)
                parts.append("")

        # Final summary
        parts.append("---")
        parts.append(
            f"*Orchestrated across {len(successful)} agents "
            f"({sum(r.tool_calls_used for r in successful.values())} total tool calls)*"
        )

        return "\n".join(parts)

    def summary(self) -> str:
        """Get full execution summary."""
        lines = ["[Orchestrator] Execution Summary:", "=" * 55]

        for step in self.plan:
            result = self.results.get(step.agent_name)
            status = step.status
            if result:
                lines.append(
                    f"  [{status}] {step.agent_name} ({result.role}): "
                    f"{result.rounds} rounds, {result.tool_calls_used} tools, "
                    f"{result.elapsed:.1f}s"
                )
            else:
                lines.append(f"  [{status}] {step.agent_name}: no result")

        lines.append("=" * 55)
        return "\n".join(lines)
