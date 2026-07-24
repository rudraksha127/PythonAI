from __future__ import annotations

from datetime import timedelta
import unittest

from src.brain.adapters.in_memory import (
    DeclarativePolicyRule,
    DefaultDenyPolicyEngine,
    InMemoryCapabilityCatalog,
    InMemoryEventPublisher,
)
from src.brain.application.mcp_execution import McpToolExecutionBlocked, McpToolExecutionGateway
from src.brain.domain.lifecycle import transition
from src.brain.domain.models import (
    PolicyAction,
    PolicyDecision,
    PolicyDecisionKind,
    PolicyRequest,
    RiskLevel,
    TrustTier,
    utc_now,
)
from src.brain.domain.workflow import (
    PlannedWorkflowTask,
    SelectedCapability,
    WorkflowPlan,
    WorkflowPlanStatus,
)
from src.brain.mcp.execution import (
    McpToolInvocationRequest,
    McpToolInvocationResponse,
)
from src.brain.mcp.installation import McpInstallationPlanBuilder, McpPackageArtifactVerification
from src.brain.mcp.probe import (
    McpProbeExecutionEvidence,
    McpProbeSnapshotBuilder,
    McpProbeTranscript,
    McpToolDescriptor,
)
from src.brain.mcp.server_manifest import McpTransportType, parse_server_manifest

from .helpers import record


SHA256_A = "sha256:" + "a" * 64
CAPABILITY_ID = "mcp.io.forgeai/example"


def active_record():
    current = record(
        CAPABILITY_ID,
        kind="tool",
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
        tags=frozenset({"mcp", "search"}),
    )
    for target in (
        "validated",
        "approved",
        "installing",
        "installed",
        "probing",
        "active",
    ):
        from src.brain.domain.models import CapabilityStatus

        current = transition(current, CapabilityStatus(target), reason=f"test {target}")
    return current


def snapshot():
    manifest = parse_server_manifest(
        {
            "name": "io.forgeai/example",
            "version": "1.0.0",
            "packages": [
                {
                    "registryType": "pypi",
                    "identifier": "forgeai-example-mcp",
                    "version": "1.0.0",
                    "transport": {"type": "stdio"},
                }
            ],
        }
    )
    plan = McpInstallationPlanBuilder.for_package(
        manifest=manifest,
        package_index=0,
        verification=McpPackageArtifactVerification(
            registry_type="pypi",
            identifier="forgeai-example-mcp",
            version="1.0.0",
            evidence_id="scan:example",
            artifact_digest=SHA256_A,
            provenance_verified=True,
        ),
        capability_id=CAPABILITY_ID,
        candidate_id="candidate:example",
        source_metadata_hash=SHA256_A,
        policy_decision=PolicyDecision(
            kind=PolicyDecisionKind.ALLOW,
            reason_code="test-allow",
            policy_version="test-v1",
        ),
    )
    started = utc_now()
    return McpProbeSnapshotBuilder.from_transcript(
        plan=plan,
        transcript=McpProbeTranscript(
            server_name="io.forgeai/example",
            protocol_version="2025-11-25",
            transport=McpTransportType.STDIO,
            execution=McpProbeExecutionEvidence(
                probe_id="probe:execution",
                isolated_runtime_id="sandbox:execution",
                credential_free=True,
                started_at=started,
                completed_at=started + timedelta(seconds=1),
            ),
            tools=(
                McpToolDescriptor(
                    name="search",
                    description="Search approved knowledge.",
                    input_schema={"type": "object"},
                ),
            ),
            resources=(),
            prompts=(),
            tools_listed=True,
            resources_listed=True,
            prompts_listed=True,
        ),
    )


def workflow(selected_capability_id: str = CAPABILITY_ID) -> WorkflowPlan:
    return WorkflowPlan(
        plan_id="workflow-plan:test",
        plan_hash=SHA256_A,
        workflow_id="workflow:test",
        goal_id="goal:test",
        status=WorkflowPlanStatus.READY,
        tasks=(
            PlannedWorkflowTask(
                task_id="research",
                agent=None,
                tools=(
                    SelectedCapability(
                        requirement_id="tool.search",
                        capability_id=selected_capability_id,
                        capability_version="1.0.0",
                        candidate_id="candidate:example",
                        artifact_digest=SHA256_A,
                    ),
                ),
                depends_on=(),
                maximum_attempts=1,
            ),
        ),
        execution_layers=(("research",),),
        blockers=(),
    )


def policy_request(*, action: PolicyAction = PolicyAction.EXECUTE, sandboxed: bool = True) -> PolicyRequest:
    return PolicyRequest(
        action=action,
        principal_id="forgeai-system",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        capability_id=CAPABILITY_ID,
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
        requested_permissions=frozenset({"network:egress:docs.example.test"}),
        sandboxed=sandboxed,
    )


class FakeInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def invoke(self, *, snapshot, tool_name: str, arguments, timeout_seconds: int) -> McpToolInvocationResponse:
        self.calls.append((tool_name, dict(arguments)))
        return McpToolInvocationResponse(
            content=[{"type": "text", "text": "untrusted search result"}],
            structured_content={"result_count": 1},
        )


class McpToolExecutionGatewayTests(unittest.TestCase):
    def _gateway(self, *, allow: bool = True):
        catalog = InMemoryCapabilityCatalog()
        catalog.create(active_record())
        events = InMemoryEventPublisher()
        rules = (
            (
                DeclarativePolicyRule(
                    rule_id="allow-sandboxed-execution",
                    effect=PolicyDecisionKind.ALLOW,
                    actions=frozenset({PolicyAction.EXECUTE}),
                    requires_sandbox=True,
                ),
            )
            if allow
            else ()
        )
        invoker = FakeInvoker()
        return (
            McpToolExecutionGateway(catalog, DefaultDenyPolicyEngine(rules), invoker, events),
            invoker,
            events,
        )

    def _request(self, **overrides) -> McpToolInvocationRequest:
        values = {
            "workflow_plan": workflow(),
            "task_id": "research",
            "snapshot": snapshot(),
            "tool_name": "search",
            "arguments": {"query": "sensitive-query-value"},
            "policy_request": policy_request(),
        }
        values.update(overrides)
        return McpToolInvocationRequest(**values)

    def test_planned_policy_approved_invocation_uses_snapshot_and_audits_hashes_not_raw_payloads(self) -> None:
        gateway, invoker, events = self._gateway()

        receipt = gateway.invoke(self._request(), correlation_id="corr-execute")

        self.assertEqual(1, len(invoker.calls))
        self.assertTrue(receipt.untrusted_output)
        self.assertTrue(receipt.arguments_hash.startswith("sha256:"))
        self.assertTrue(receipt.output_hash.startswith("sha256:"))
        self.assertEqual(
            ["mcp.tool.invocation.started.v1", "mcp.tool.invocation.completed.v1"],
            [event.event_type for event in events.events()],
        )
        self.assertNotIn("sensitive-query-value", str([dict(event.payload) for event in events.events()]))

    def test_default_deny_blocks_before_invoker_and_emits_a_safe_audit_event(self) -> None:
        gateway, invoker, events = self._gateway(allow=False)

        with self.assertRaises(McpToolExecutionBlocked) as blocked:
            gateway.invoke(self._request(), correlation_id="corr-deny")

        self.assertEqual("no-matching-policy-rule", blocked.exception.reason_code)
        self.assertEqual([], invoker.calls)
        self.assertEqual(["mcp.tool.invocation.blocked.v1"], [event.event_type for event in events.events()])

    def test_unplanned_capability_or_nonexecute_policy_action_never_reaches_invoker(self) -> None:
        gateway, invoker, _ = self._gateway()

        with self.assertRaises(McpToolExecutionBlocked) as unplanned:
            gateway.invoke(
                self._request(workflow_plan=workflow("different.capability")),
                correlation_id="corr-unplanned",
            )
        self.assertEqual("snapshot-capability-not-selected-for-task", unplanned.exception.reason_code)

        with self.assertRaises(McpToolExecutionBlocked) as wrong_action:
            gateway.invoke(
                self._request(policy_request=policy_request(action=PolicyAction.DISCOVER)),
                correlation_id="corr-wrong-action",
            )
        self.assertEqual("execution-policy-action-required", wrong_action.exception.reason_code)
        self.assertEqual([], invoker.calls)

    def test_inactive_capability_cannot_execute_even_if_snapshot_and_policy_are_valid(self) -> None:
        catalog = InMemoryCapabilityCatalog()
        catalog.create(record(CAPABILITY_ID, kind="tool", tags=frozenset({"mcp", "search"})))
        events = InMemoryEventPublisher()
        invoker = FakeInvoker()
        policy = DefaultDenyPolicyEngine(
            [
                DeclarativePolicyRule(
                    rule_id="allow-execute",
                    effect=PolicyDecisionKind.ALLOW,
                    actions=frozenset({PolicyAction.EXECUTE}),
                )
            ]
        )
        gateway = McpToolExecutionGateway(catalog, policy, invoker, events)

        with self.assertRaises(McpToolExecutionBlocked) as blocked:
            gateway.invoke(self._request(), correlation_id="corr-inactive")
        self.assertEqual("snapshot-capability-not-active", blocked.exception.reason_code)
        self.assertEqual([], invoker.calls)

