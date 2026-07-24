from __future__ import annotations

import unittest

from src.brain.adapters.in_memory import InMemoryCapabilityCatalog, InMemoryEventPublisher
from src.brain.application.services import CapabilityResolver
from src.brain.application.workflow_planning import WorkflowPlanner
from src.brain.domain.lifecycle import transition
from src.brain.domain.models import CapabilityRequirement, CapabilityStatus, RiskLevel, TrustTier
from src.brain.domain.workflow import (
    WorkflowDefinition,
    WorkflowGoal,
    WorkflowPlanStatus,
    WorkflowTaskDefinition,
    WorkflowValidationError,
)

from .helpers import record


def active_capability(
    capability_id: str,
    *,
    kind: str,
    tags: frozenset[str],
) -> object:
    current = record(
        capability_id,
        kind=kind,
        tags=tags,
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
    )
    for target in (
        CapabilityStatus.VALIDATED,
        CapabilityStatus.APPROVED,
        CapabilityStatus.INSTALLING,
        CapabilityStatus.INSTALLED,
        CapabilityStatus.PROBING,
        CapabilityStatus.ACTIVE,
    ):
        current = transition(current, target, reason=f"test transition to {target.value}")
    return current


def workflow() -> WorkflowDefinition:
    research_agent = CapabilityRequirement(
        requirement_id="agent.research",
        kind="agent",
        required_tags=frozenset({"research"}),
    )
    writer_agent = CapabilityRequirement(
        requirement_id="agent.writer",
        kind="agent",
        required_tags=frozenset({"writing"}),
    )
    search_tool = CapabilityRequirement(
        requirement_id="tool.knowledge-search",
        kind="tool",
        required_tags=frozenset({"knowledge", "search"}),
    )
    return WorkflowDefinition(
        workflow_id="workflow:research-brief",
        goal=WorkflowGoal(
            goal_id="goal:research-brief",
            title="Prepare a research brief",
            description="Gather approved knowledge and synthesize a cited brief.",
        ),
        tasks=(
            WorkflowTaskDefinition(
                task_id="research",
                title="Research",
                objective="Collect relevant approved material.",
                agent_requirement=research_agent,
                tool_requirements=(search_tool,),
                validation_checks=("citations-present",),
                maximum_attempts=2,
            ),
            WorkflowTaskDefinition(
                task_id="write",
                title="Write",
                objective="Synthesize the research into a concise brief.",
                depends_on=("research",),
                agent_requirement=writer_agent,
                validation_checks=("review-complete",),
            ),
        ),
    )


class WorkflowPlanningTests(unittest.TestCase):
    def test_dynamic_active_agents_and_tools_are_resolved_into_a_ready_dag(self) -> None:
        catalog = InMemoryCapabilityCatalog()
        catalog.create(
            active_capability(
                "agent.researcher",
                kind="agent",
                tags=frozenset({"research", "web"}),
            )
        )
        catalog.create(
            active_capability(
                "agent.writer",
                kind="agent",
                tags=frozenset({"writing", "review"}),
            )
        )
        catalog.create(
            active_capability(
                "tool.knowledge-search",
                kind="tool",
                tags=frozenset({"knowledge", "search"}),
            )
        )
        events = InMemoryEventPublisher()
        planner = WorkflowPlanner(CapabilityResolver(catalog), events)

        plan = planner.plan(
            workflow(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="corr-plan",
        )

        self.assertTrue(plan.ready_for_execution)
        self.assertEqual(WorkflowPlanStatus.READY, plan.status)
        self.assertEqual((("research",), ("write",)), plan.execution_layers)
        research = next(task for task in plan.tasks if task.task_id == "research")
        self.assertEqual("agent.researcher", research.agent.capability_id)  # type: ignore[union-attr]
        self.assertEqual(("tool.knowledge-search",), tuple(tool.capability_id for tool in research.tools))
        self.assertEqual("workflow.plan.created.v1", events.events()[0].event_type)
        self.assertEqual("ready", events.events()[0].payload["status"])

    def test_missing_capability_creates_a_blocked_plan_instead_of_executing_or_guessing(self) -> None:
        catalog = InMemoryCapabilityCatalog()
        catalog.create(
            active_capability(
                "agent.researcher",
                kind="agent",
                tags=frozenset({"research"}),
            )
        )
        events = InMemoryEventPublisher()
        planner = WorkflowPlanner(CapabilityResolver(catalog), events)

        plan = planner.plan(
            workflow(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="corr-blocked",
        )

        self.assertFalse(plan.ready_for_execution)
        self.assertEqual(WorkflowPlanStatus.BLOCKED, plan.status)
        self.assertEqual(
            {"agent.writer", "tool.knowledge-search"},
            {blocker.requirement_id for blocker in plan.blockers},
        )
        self.assertEqual("blocked", events.events()[0].payload["status"])

    def test_cyclic_dependency_graph_is_rejected_before_any_plan_event_is_emitted(self) -> None:
        catalog = InMemoryCapabilityCatalog()
        events = InMemoryEventPublisher()
        planner = WorkflowPlanner(CapabilityResolver(catalog), events)
        cyclic = WorkflowDefinition(
            workflow_id="workflow:cycle",
            goal=WorkflowGoal(goal_id="goal:cycle", title="Cycle", description="Must be rejected."),
            tasks=(
                WorkflowTaskDefinition(
                    task_id="first", title="First", objective="First task", depends_on=("second",)
                ),
                WorkflowTaskDefinition(
                    task_id="second", title="Second", objective="Second task", depends_on=("first",)
                ),
            ),
        )

        with self.assertRaises(WorkflowValidationError):
            planner.plan(
                cyclic,
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="corr-cycle",
            )
        self.assertEqual((), events.events())

    def test_same_definition_and_catalog_produce_a_stable_content_hash(self) -> None:
        catalog = InMemoryCapabilityCatalog()
        catalog.create(
            active_capability("agent.researcher", kind="agent", tags=frozenset({"research"}))
        )
        catalog.create(active_capability("agent.writer", kind="agent", tags=frozenset({"writing"})))
        catalog.create(
            active_capability("tool.knowledge-search", kind="tool", tags=frozenset({"knowledge", "search"}))
        )
        planner = WorkflowPlanner(CapabilityResolver(catalog), InMemoryEventPublisher())

        first = planner.plan(
            workflow(), tenant_id="tenant-a", workspace_id="workspace-a", correlation_id="corr-first"
        )
        second = planner.plan(
            workflow(), tenant_id="tenant-a", workspace_id="workspace-a", correlation_id="corr-second"
        )
        self.assertNotEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.plan_hash, second.plan_hash)

