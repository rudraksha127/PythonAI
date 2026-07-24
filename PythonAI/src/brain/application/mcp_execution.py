"""Plan-first, policy-bound MCP tool execution gateway."""

from __future__ import annotations

from ..domain.events import new_event
from ..domain.models import CapabilityStatus, PolicyAction, PolicyDecision, PolicyDecisionKind
from ..mcp.execution import (
    McpToolExecutionReceipt,
    McpToolInvocationRequest,
    McpToolInvocationResponse,
    McpToolInvokerPort,
    new_execution_id,
    payload_digest,
)
from .ports import CapabilityCatalogPort, EventPublisherPort, PolicyEnginePort


class McpToolExecutionBlocked(PermissionError):
    """Raised when plan, catalog, or policy controls prevent a tool call."""

    def __init__(self, reason_code: str, decision: PolicyDecision | None = None) -> None:
        super().__init__(f"MCP tool execution blocked: {reason_code}")
        self.reason_code = reason_code
        self.decision = decision


class McpToolExecutionGateway:
    """The only application path allowed to invoke a tool from an MCP snapshot."""

    def __init__(
        self,
        catalog: CapabilityCatalogPort,
        policy_engine: PolicyEnginePort,
        invoker: McpToolInvokerPort,
        events: EventPublisherPort,
    ) -> None:
        self._catalog = catalog
        self._policy_engine = policy_engine
        self._invoker = invoker
        self._events = events

    def invoke(self, request: McpToolInvocationRequest, *, correlation_id: str) -> McpToolExecutionReceipt:
        """Validate the plan and policy, invoke once, and record only payload hashes."""

        task = self._planned_task(request)
        self._ensure_snapshot_tool(request)
        record = self._active_record(request)
        self._ensure_policy_facts(request, record)
        arguments_hash, arguments_bytes = payload_digest(
            request.arguments,
            field_name="invocation.arguments",
            maximum_bytes=128_000,
        )
        decision = self._policy_engine.decide(request.policy_request)
        if not decision.permits_progress:
            self._publish_blocked(request, correlation_id, arguments_hash, arguments_bytes, decision)
            raise McpToolExecutionBlocked(decision.reason_code, decision)
        if decision.kind is PolicyDecisionKind.REQUIRE_SANDBOX and not request.policy_request.sandboxed:
            sandbox_decision = PolicyDecision(
                kind=PolicyDecisionKind.DENY,
                reason_code="sandbox-required",
                policy_version=decision.policy_version,
                rule_id=decision.rule_id,
                obligations=decision.obligations,
            )
            self._publish_blocked(request, correlation_id, arguments_hash, arguments_bytes, sandbox_decision)
            raise McpToolExecutionBlocked("sandbox-required", sandbox_decision)
        execution_id = new_execution_id()
        self._events.publish(
            new_event(
                event_type="mcp.tool.invocation.started.v1",
                tenant_id=request.policy_request.tenant_id,
                workspace_id=request.policy_request.workspace_id,
                subject_id=request.snapshot.capability_id,
                correlation_id=correlation_id,
                payload={
                    "execution_id": execution_id,
                    "workflow_plan_id": request.workflow_plan.plan_id,
                    "task_id": task.task_id,
                    "snapshot_id": request.snapshot.snapshot_id,
                    "tool_name": request.tool_name,
                    "arguments_hash": arguments_hash,
                    "arguments_bytes": arguments_bytes,
                    "timeout_seconds": request.timeout_seconds,
                    "policy": self._policy_payload(decision),
                },
            )
        )
        try:
            response = self._invoker.invoke(
                snapshot=request.snapshot,
                tool_name=request.tool_name,
                arguments=request.arguments,
                timeout_seconds=request.timeout_seconds,
            )
            if not isinstance(response, McpToolInvocationResponse):
                raise TypeError("MCP tool invoker must return McpToolInvocationResponse")
            output_hash, output_bytes = payload_digest(
                {
                    "content": response.content,
                    "is_error": response.is_error,
                    "structured_content": response.structured_content,
                    "metadata": response.metadata,
                },
                field_name="tool response",
                maximum_bytes=1_000_000,
            )
            receipt = McpToolExecutionReceipt(
                execution_id=execution_id,
                arguments_hash=arguments_hash,
                arguments_bytes=arguments_bytes,
                output_hash=output_hash,
                output_bytes=output_bytes,
                response=response,
            )
            self._events.publish(
                new_event(
                    event_type="mcp.tool.invocation.completed.v1",
                    tenant_id=request.policy_request.tenant_id,
                    workspace_id=request.policy_request.workspace_id,
                    subject_id=request.snapshot.capability_id,
                    correlation_id=correlation_id,
                    payload={
                        "execution_id": execution_id,
                        "workflow_plan_id": request.workflow_plan.plan_id,
                        "task_id": task.task_id,
                        "snapshot_id": request.snapshot.snapshot_id,
                        "tool_name": request.tool_name,
                        "arguments_hash": arguments_hash,
                        "arguments_bytes": arguments_bytes,
                        "output_hash": output_hash,
                        "output_bytes": output_bytes,
                        "tool_reported_error": response.is_error,
                        "untrusted_output": receipt.untrusted_output,
                    },
                )
            )
            return receipt
        except Exception as error:
            self._events.publish(
                new_event(
                    event_type="mcp.tool.invocation.failed.v1",
                    tenant_id=request.policy_request.tenant_id,
                    workspace_id=request.policy_request.workspace_id,
                    subject_id=request.snapshot.capability_id,
                    correlation_id=correlation_id,
                    payload={
                        "execution_id": execution_id,
                        "workflow_plan_id": request.workflow_plan.plan_id,
                        "task_id": task.task_id,
                        "tool_name": request.tool_name,
                        "arguments_hash": arguments_hash,
                        "arguments_bytes": arguments_bytes,
                        "error_type": type(error).__name__,
                    },
                )
            )
            raise

    def _planned_task(self, request: McpToolInvocationRequest):
        if not request.workflow_plan.ready_for_execution:
            raise McpToolExecutionBlocked("workflow-plan-not-ready")
        task = next((item for item in request.workflow_plan.tasks if item.task_id == request.task_id), None)
        if task is None:
            raise McpToolExecutionBlocked("task-not-in-workflow-plan")
        if request.snapshot.capability_id not in {tool.capability_id for tool in task.tools}:
            raise McpToolExecutionBlocked("snapshot-capability-not-selected-for-task")
        return task

    @staticmethod
    def _ensure_snapshot_tool(request: McpToolInvocationRequest) -> None:
        if request.tool_name not in {tool.name for tool in request.snapshot.tools}:
            raise McpToolExecutionBlocked("tool-not-in-immutable-snapshot")

    def _active_record(self, request: McpToolInvocationRequest):
        record = self._catalog.get(request.snapshot.capability_id)
        if record is None:
            raise McpToolExecutionBlocked("snapshot-capability-not-in-catalog")
        if record.status is not CapabilityStatus.ACTIVE:
            raise McpToolExecutionBlocked("snapshot-capability-not-active")
        return record

    @staticmethod
    def _ensure_policy_facts(request: McpToolInvocationRequest, record) -> None:
        policy = request.policy_request
        if policy.action is not PolicyAction.EXECUTE:
            raise McpToolExecutionBlocked("execution-policy-action-required")
        if policy.capability_id != request.snapshot.capability_id:
            raise McpToolExecutionBlocked("policy-capability-mismatch")
        if policy.risk_level is not record.descriptor.risk_level:
            raise McpToolExecutionBlocked("policy-risk-level-mismatch")
        if policy.trust_tier is not record.candidate.trust_tier:
            raise McpToolExecutionBlocked("policy-trust-tier-mismatch")
        if policy.requested_permissions != record.descriptor.required_permissions:
            raise McpToolExecutionBlocked("policy-permissions-mismatch")
        if not policy.sandboxed:
            raise McpToolExecutionBlocked("sandbox-baseline-required")

    def _publish_blocked(
        self,
        request: McpToolInvocationRequest,
        correlation_id: str,
        arguments_hash: str,
        arguments_bytes: int,
        decision: PolicyDecision,
    ) -> None:
        self._events.publish(
            new_event(
                event_type="mcp.tool.invocation.blocked.v1",
                tenant_id=request.policy_request.tenant_id,
                workspace_id=request.policy_request.workspace_id,
                subject_id=request.snapshot.capability_id,
                correlation_id=correlation_id,
                payload={
                    "workflow_plan_id": request.workflow_plan.plan_id,
                    "task_id": request.task_id,
                    "snapshot_id": request.snapshot.snapshot_id,
                    "tool_name": request.tool_name,
                    "arguments_hash": arguments_hash,
                    "arguments_bytes": arguments_bytes,
                    "policy": self._policy_payload(decision),
                },
            )
        )

    @staticmethod
    def _policy_payload(decision: PolicyDecision) -> dict[str, str | None]:
        return {
            "decision": decision.kind.value,
            "reason_code": decision.reason_code,
            "policy_version": decision.policy_version,
            "rule_id": decision.rule_id,
        }
