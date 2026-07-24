"""Dynamic, non-executing workflow planning over ForgeAI's capability catalog."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from ..domain.events import new_event
from ..domain.workflow import (
    PlannedWorkflowTask,
    SelectedCapability,
    UnsatisfiedRequirement,
    WorkflowDefinition,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowValidationError,
)
from .ports import EventPublisherPort
from .services import CapabilityResolver, ResolvedCapability


class WorkflowPlanner:
    """Resolve agent/tool requirements and validate a dependency DAG without execution."""

    def __init__(self, resolver: CapabilityResolver, events: EventPublisherPort) -> None:
        self._resolver = resolver
        self._events = events

    def plan(
        self,
        workflow: WorkflowDefinition,
        *,
        tenant_id: str,
        workspace_id: str,
        correlation_id: str,
    ) -> WorkflowPlan:
        """Create an immutable plan from currently active, policy-approved capabilities."""

        layers = self._execution_layers(workflow)
        planned_tasks: list[PlannedWorkflowTask] = []
        blockers: list[UnsatisfiedRequirement] = []
        for task in workflow.tasks:
            agent: SelectedCapability | None = None
            if task.agent_requirement is not None:
                agent = self._selected(task.agent_requirement)
                if agent is None:
                    blockers.append(
                        UnsatisfiedRequirement(
                            task_id=task.task_id,
                            requirement_id=task.agent_requirement.requirement_id,
                            role="agent",
                        )
                    )
            tools: list[SelectedCapability] = []
            for requirement in task.tool_requirements:
                selected = self._selected(requirement)
                if selected is None:
                    blockers.append(
                        UnsatisfiedRequirement(
                            task_id=task.task_id,
                            requirement_id=requirement.requirement_id,
                            role="tool",
                        )
                    )
                else:
                    tools.append(selected)
            planned_tasks.append(
                PlannedWorkflowTask(
                    task_id=task.task_id,
                    agent=agent,
                    tools=tuple(tools),
                    depends_on=task.depends_on,
                    maximum_attempts=task.maximum_attempts,
                )
            )
        status = WorkflowPlanStatus.BLOCKED if blockers else WorkflowPlanStatus.READY
        plan_hash = self._plan_hash(workflow, planned_tasks, layers, blockers)
        plan = WorkflowPlan(
            plan_id=f"workflow-plan:{uuid4()}",
            plan_hash=plan_hash,
            workflow_id=workflow.workflow_id,
            goal_id=workflow.goal.goal_id,
            status=status,
            tasks=tuple(planned_tasks),
            execution_layers=layers,
            blockers=tuple(blockers),
        )
        self._events.publish(
            new_event(
                event_type="workflow.plan.created.v1",
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                subject_id=workflow.goal.goal_id,
                correlation_id=correlation_id,
                payload={
                    "plan_id": plan.plan_id,
                    "plan_hash": plan.plan_hash,
                    "workflow_id": plan.workflow_id,
                    "status": plan.status.value,
                    "task_count": len(plan.tasks),
                    "execution_layers": plan.execution_layers,
                    "blocker_count": len(plan.blockers),
                    "blockers": tuple(
                        {
                            "task_id": blocker.task_id,
                            "requirement_id": blocker.requirement_id,
                            "role": blocker.role,
                            "reason_code": blocker.reason_code,
                        }
                        for blocker in plan.blockers
                    ),
                    "selected_capability_ids": tuple(
                        sorted(
                            {
                                selected.capability_id
                                for task in plan.tasks
                                for selected in ((task.agent,) if task.agent else ()) + task.tools
                            }
                        )
                    ),
                },
            )
        )
        return plan

    def _selected(self, requirement: Any) -> SelectedCapability | None:
        resolved = self._resolver.resolve(requirement)
        if resolved is None:
            return None
        return self._selection_from_resolved(requirement.requirement_id, resolved)

    @staticmethod
    def _selection_from_resolved(requirement_id: str, resolved: ResolvedCapability) -> SelectedCapability:
        record = resolved.record
        return SelectedCapability(
            requirement_id=requirement_id,
            capability_id=record.capability_id,
            capability_version=record.descriptor.version,
            candidate_id=record.candidate.candidate_id,
            artifact_digest=record.candidate.artifact.digest,
        )

    @staticmethod
    def _execution_layers(workflow: WorkflowDefinition) -> tuple[tuple[str, ...], ...]:
        remaining = {task.task_id: set(task.depends_on) for task in workflow.tasks}
        completed: set[str] = set()
        layers: list[tuple[str, ...]] = []
        while remaining:
            layer = tuple(sorted(task_id for task_id, dependencies in remaining.items() if dependencies <= completed))
            if not layer:
                cycle_nodes = ", ".join(sorted(remaining))
                raise WorkflowValidationError(f"workflow dependency graph contains a cycle: {cycle_nodes}")
            layers.append(layer)
            completed.update(layer)
            for task_id in layer:
                del remaining[task_id]
        return tuple(layers)

    @staticmethod
    def _plan_hash(
        workflow: WorkflowDefinition,
        tasks: list[PlannedWorkflowTask],
        layers: tuple[tuple[str, ...], ...],
        blockers: list[UnsatisfiedRequirement],
    ) -> str:
        payload = {
            "workflow_id": workflow.workflow_id,
            "version": workflow.version,
            "goal_id": workflow.goal.goal_id,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "agent": None
                    if task.agent is None
                    else {
                        "requirement_id": task.agent.requirement_id,
                        "capability_id": task.agent.capability_id,
                        "capability_version": task.agent.capability_version,
                        "candidate_id": task.agent.candidate_id,
                        "artifact_digest": task.agent.artifact_digest,
                    },
                    "tools": [
                        {
                            "requirement_id": tool.requirement_id,
                            "capability_id": tool.capability_id,
                            "capability_version": tool.capability_version,
                            "candidate_id": tool.candidate_id,
                            "artifact_digest": tool.artifact_digest,
                        }
                        for tool in task.tools
                    ],
                    "depends_on": task.depends_on,
                    "maximum_attempts": task.maximum_attempts,
                }
                for task in tasks
            ],
            "layers": layers,
            "blockers": [
                {
                    "task_id": blocker.task_id,
                    "requirement_id": blocker.requirement_id,
                    "role": blocker.role,
                    "reason_code": blocker.reason_code,
                }
                for blocker in blockers
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
