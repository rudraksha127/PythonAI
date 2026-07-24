"""Vendor-neutral workflow planning contracts for ForgeAI Brain.

Goals, agents, and tools are described as requirements rather than hardcoded
implementations. The application planner resolves those requirements from the
active capability catalog and returns a DAG plan; a separate executor is
required to run it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from .models import CapabilityRequirement, freeze_mapping, utc_now


class WorkflowValidationError(ValueError):
    """Raised when a workflow definition or plan violates core invariants."""


class WorkflowPlanStatus(str, Enum):
    """A plan is executable only after all dynamic requirements resolve."""

    READY = "ready"
    BLOCKED = "blocked"


def _text(field_name: str, value: str, *, maximum: int = 10_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowValidationError(f"{field_name} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum:
        raise WorkflowValidationError(f"{field_name} exceeds the maximum length")
    return result


def _identifiers(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(_text(field_name, value, maximum=256) for value in values)
    if len(set(normalized)) != len(normalized):
        raise WorkflowValidationError(f"{field_name} values must be unique")
    return normalized


@dataclass(frozen=True, slots=True)
class WorkflowGoal:
    """A user or automation goal that must be planned before execution."""

    goal_id: str
    title: str
    description: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _text("goal.goal_id", self.goal_id, maximum=256))
        object.__setattr__(self, "title", _text("goal.title", self.title, maximum=512))
        object.__setattr__(self, "description", _text("goal.description", self.description))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class WorkflowTaskDefinition:
    """One DAG node expressed only through role and capability requirements."""

    task_id: str
    title: str
    objective: str
    depends_on: tuple[str, ...] = ()
    agent_requirement: CapabilityRequirement | None = None
    tool_requirements: tuple[CapabilityRequirement, ...] = ()
    validation_checks: tuple[str, ...] = ()
    maximum_attempts: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("task.task_id", self.task_id, maximum=256))
        object.__setattr__(self, "title", _text("task.title", self.title, maximum=512))
        object.__setattr__(self, "objective", _text("task.objective", self.objective))
        object.__setattr__(self, "depends_on", _identifiers("task.depends_on", tuple(self.depends_on)))
        object.__setattr__(
            self,
            "validation_checks",
            _identifiers("task.validation_checks", tuple(self.validation_checks)),
        )
        object.__setattr__(self, "tool_requirements", tuple(self.tool_requirements))
        if self.task_id in self.depends_on:
            raise WorkflowValidationError("task may not depend on itself")
        if self.agent_requirement is not None and not isinstance(
            self.agent_requirement, CapabilityRequirement
        ):
            raise WorkflowValidationError("task.agent_requirement must be a capability requirement")
        if any(not isinstance(requirement, CapabilityRequirement) for requirement in self.tool_requirements):
            raise WorkflowValidationError("task.tool_requirements must contain capability requirements")
        requirement_ids = [requirement.requirement_id for requirement in self.tool_requirements]
        if len(set(requirement_ids)) != len(requirement_ids):
            raise WorkflowValidationError("task.tool_requirements must use unique requirement IDs")
        if not isinstance(self.maximum_attempts, int) or isinstance(self.maximum_attempts, bool):
            raise WorkflowValidationError("task.maximum_attempts must be an integer")
        if not 1 <= self.maximum_attempts <= 20:
            raise WorkflowValidationError("task.maximum_attempts must be between 1 and 20")


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """A declarative task graph produced by a goal-decomposer extension or user."""

    workflow_id: str
    goal: WorkflowGoal
    tasks: tuple[WorkflowTaskDefinition, ...]
    version: str = "forgeai.dev/workflow/v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workflow_id", _text("workflow.workflow_id", self.workflow_id, maximum=256))
        object.__setattr__(self, "version", _text("workflow.version", self.version, maximum=256))
        if not isinstance(self.goal, WorkflowGoal):
            raise WorkflowValidationError("workflow.goal must be a workflow goal")
        object.__setattr__(self, "tasks", tuple(self.tasks))
        if not self.tasks:
            raise WorkflowValidationError("workflow.tasks must not be empty")
        if any(not isinstance(task, WorkflowTaskDefinition) for task in self.tasks):
            raise WorkflowValidationError("workflow.tasks must contain task definitions")
        task_ids = [task.task_id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            raise WorkflowValidationError("workflow task IDs must be unique")
        available = frozenset(task_ids)
        for task in self.tasks:
            unknown = set(task.depends_on) - available
            if unknown:
                raise WorkflowValidationError(
                    f"task {task.task_id!r} depends on undeclared tasks: {', '.join(sorted(unknown))}"
                )
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class SelectedCapability:
    """Provenance-pinned catalog selection used in a generated workflow plan."""

    requirement_id: str
    capability_id: str
    capability_version: str
    candidate_id: str
    artifact_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _text("selection.requirement_id", self.requirement_id, maximum=256))
        object.__setattr__(self, "capability_id", _text("selection.capability_id", self.capability_id, maximum=512))
        object.__setattr__(self, "capability_version", _text("selection.capability_version", self.capability_version, maximum=256))
        object.__setattr__(self, "candidate_id", _text("selection.candidate_id", self.candidate_id, maximum=512))
        if self.artifact_digest is not None:
            object.__setattr__(
                self,
                "artifact_digest",
                _text("selection.artifact_digest", self.artifact_digest, maximum=512),
            )


@dataclass(frozen=True, slots=True)
class UnsatisfiedRequirement:
    """An explainable reason a workflow plan cannot yet be executed."""

    task_id: str
    requirement_id: str
    role: str
    reason_code: str = "no-active-capability"

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("blocker.task_id", self.task_id, maximum=256))
        object.__setattr__(self, "requirement_id", _text("blocker.requirement_id", self.requirement_id, maximum=256))
        object.__setattr__(self, "role", _text("blocker.role", self.role, maximum=64))
        object.__setattr__(self, "reason_code", _text("blocker.reason_code", self.reason_code, maximum=256))


@dataclass(frozen=True, slots=True)
class PlannedWorkflowTask:
    """A task with dynamically selected active agent/tool capabilities."""

    task_id: str
    agent: SelectedCapability | None
    tools: tuple[SelectedCapability, ...]
    depends_on: tuple[str, ...]
    maximum_attempts: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("planned_task.task_id", self.task_id, maximum=256))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "depends_on", _identifiers("planned_task.depends_on", tuple(self.depends_on)))
        if self.agent is not None and not isinstance(self.agent, SelectedCapability):
            raise WorkflowValidationError("planned_task.agent must be a selected capability")
        if any(not isinstance(tool, SelectedCapability) for tool in self.tools):
            raise WorkflowValidationError("planned_task.tools must contain selected capabilities")
        if not isinstance(self.maximum_attempts, int) or self.maximum_attempts < 1:
            raise WorkflowValidationError("planned_task.maximum_attempts must be a positive integer")


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    """Immutable, hash-addressed execution plan; this type has no execute method."""

    plan_id: str
    plan_hash: str
    workflow_id: str
    goal_id: str
    status: WorkflowPlanStatus
    tasks: tuple[PlannedWorkflowTask, ...]
    execution_layers: tuple[tuple[str, ...], ...]
    blockers: tuple[UnsatisfiedRequirement, ...]
    generated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text("plan.plan_id", self.plan_id, maximum=256))
        object.__setattr__(self, "plan_hash", _text("plan.plan_hash", self.plan_hash, maximum=256))
        object.__setattr__(self, "workflow_id", _text("plan.workflow_id", self.workflow_id, maximum=256))
        object.__setattr__(self, "goal_id", _text("plan.goal_id", self.goal_id, maximum=256))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "execution_layers", tuple(tuple(layer) for layer in self.execution_layers))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        if not self.tasks:
            raise WorkflowValidationError("plan.tasks must not be empty")
        if any(not isinstance(task, PlannedWorkflowTask) for task in self.tasks):
            raise WorkflowValidationError("plan.tasks must contain planned tasks")
        if any(not isinstance(blocker, UnsatisfiedRequirement) for blocker in self.blockers):
            raise WorkflowValidationError("plan.blockers must contain unsatisfied requirements")
        planned_ids = {task.task_id for task in self.tasks}
        layered_ids = tuple(task_id for layer in self.execution_layers for task_id in layer)
        if set(layered_ids) != planned_ids or len(layered_ids) != len(planned_ids):
            raise WorkflowValidationError("plan.execution_layers must contain every planned task exactly once")
        if self.status is WorkflowPlanStatus.READY and self.blockers:
            raise WorkflowValidationError("a ready plan may not have blockers")
        if self.status is WorkflowPlanStatus.BLOCKED and not self.blockers:
            raise WorkflowValidationError("a blocked plan requires blockers")
        if self.generated_at.tzinfo is None:
            raise WorkflowValidationError("plan.generated_at must be timezone-aware")

    @property
    def ready_for_execution(self) -> bool:
        """Execution gateways must require this property before scheduling work."""

        return self.status is WorkflowPlanStatus.READY
