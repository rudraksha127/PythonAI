"""
PythonAI Agentic System — AgentSwarm
======================================
Manages multiple SubAgents that run concurrently on independent sub-tasks.
Handles dependencies, result collection, and parallel execution.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .sub_agent import SubAgent, SubAgentResult


class AgentSwarm:
    """Manages a group of SubAgents for parallel execution.

    Features:
      - Run multiple SubAgents concurrently
      - Dependency ordering between agents
      - Result collection and merging
      - Timeout management
    """

    def __init__(
        self,
        agents: list[SubAgent] | None = None,
        max_concurrent: int = 4,
        on_agent_start: Any = None,
        on_agent_complete: Any = None,
    ):
        self.agents: dict[str, SubAgent] = {}
        if agents:
            for a in agents:
                self.agents[a.name] = a
        self.max_concurrent = max_concurrent
        self.on_agent_start = on_agent_start
        self.on_agent_complete = on_agent_complete
        self.results: dict[str, SubAgentResult] = {}

    def add_agent(self, agent: SubAgent) -> None:
        """Register a sub-agent."""
        self.agents[agent.name] = agent

    def get_agent(self, name: str) -> SubAgent | None:
        """Get a sub-agent by name."""
        return self.agents.get(name)

    def run_all(
        self,
        tasks: dict[str, str],
        contexts: dict[str, str | None] | None = None,
    ) -> dict[str, SubAgentResult]:
        """Run multiple sub-agents in parallel with their tasks.

        Args:
            tasks: Mapping of agent_name -> task_description
            contexts: Optional mapping of agent_name -> context_string

        Returns:
            Mapping of agent_name -> SubAgentResult
        """
        self.results = {}
        contexts = contexts or {}

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            future_map = {}

            for agent_name, task in tasks.items():
                agent = self.agents.get(agent_name)
                if not agent:
                    self.results[agent_name] = SubAgentResult(
                        agent_name=agent_name, role="",
                        success=False, output="", error=f"Agent '{agent_name}' not found",
                    )
                    continue

                if self.on_agent_start:
                    self.on_agent_start(agent_name)

                context = contexts.get(agent_name)
                future = executor.submit(agent.run, task, context)
                future_map[future] = agent_name

            for future in as_completed(future_map):
                agent_name = future_map[future]
                try:
                    result = future.result(timeout=120)
                    self.results[agent_name] = result
                except Exception as e:
                    self.results[agent_name] = SubAgentResult(
                        agent_name=agent_name, role="",
                        success=False, output="", error=str(e),
                    )

                if self.on_agent_complete:
                    self.on_agent_complete(agent_name, self.results[agent_name])

        return self.results

    def run_sequential(
        self,
        pipeline: list[tuple[str, str]],
        shared_context: str | None = None,
    ) -> dict[str, SubAgentResult]:
        """Run sub-agents sequentially, passing results as context.

        Args:
            pipeline: List of (agent_name, task_description) in execution order
            shared_context: Optional base context

        Returns:
            Mapping of agent_name -> SubAgentResult
        """
        self.results = {}
        accumulated_context = shared_context or ""

        for agent_name, task in pipeline:
            agent = self.agents.get(agent_name)
            if not agent:
                self.results[agent_name] = SubAgentResult(
                    agent_name=agent_name, role="",
                    success=False, output="", error=f"Agent '{agent_name}' not found",
                )
                continue

            if self.on_agent_start:
                self.on_agent_start(agent_name)

            result = agent.run(task, accumulated_context)
            self.results[agent_name] = result

            if result.success and result.output:
                accumulated_context += f"\n\n[{agent_name} output]:\n{result.output[:2000]}\n"

            if self.on_agent_complete:
                self.on_agent_complete(agent_name, result)

        return self.results

    def collect_outputs(self) -> dict[str, str]:
        """Collect successful outputs from all agents."""
        return {
            name: result.output
            for name, result in self.results.items()
            if result.success
        }

    def summary(self) -> str:
        """Get a human-readable summary of all agent results."""
        lines = ["[AgentSwarm] Results:", "=" * 55]
        for name, result in self.results.items():
            status = "[OK]" if result.success else "[FAIL]"
            lines.append(
                f"  {status} {name} ({result.role}): "
                f"{result.rounds} rounds, {result.tool_calls_used} tools, "
                f"{result.tokens_used} tokens, {result.elapsed:.1f}s"
            )
            if result.error:
                lines.append(f"       Error: {result.error[:100]}")
        lines.append("=" * 55)
        return "\n".join(lines)

    @property
    def total_tool_calls(self) -> int:
        return sum(r.tool_calls_used for r in self.results.values())

    @property
    def total_tokens(self) -> int:
        return sum(r.tokens_used for r in self.results.values())
