"""Application service for policy-gated MCP installation planning.

This is intentionally a planning boundary. A future installer consumes only
``McpInstallationPlan.ready_for_sandbox_execution`` plans and must still run
its own digest check, isolated install, credential-free probe, and activation
transitions.
"""

from __future__ import annotations

from ..domain.events import new_event
from ..domain.models import PolicyAction, PolicyDecision, PolicyDecisionKind, PolicyRequest
from ..mcp.installation import (
    McpInstallationPlan,
    McpInstallationPlanBuilder,
    McpPackageArtifactVerification,
    McpRemoteEndpointVerification,
)
from ..mcp.server_manifest import McpServerManifest
from .ports import EventPublisherPort, PolicyEnginePort


class McpInstallationBlocked(PermissionError):
    """Raised when policy or ForgeAI's sandbox baseline forbids a plan."""

    def __init__(self, reason_code: str, decision: PolicyDecision | None = None) -> None:
        super().__init__(f"MCP installation planning blocked: {reason_code}")
        self.reason_code = reason_code
        self.decision = decision


class McpInstallationPlanningService:
    """Evaluate install policy, build a non-executing plan, and emit an audit event."""

    def __init__(self, policy_engine: PolicyEnginePort, events: EventPublisherPort) -> None:
        self._policy_engine = policy_engine
        self._events = events

    def plan_package(
        self,
        *,
        manifest: McpServerManifest,
        package_index: int,
        verification: McpPackageArtifactVerification,
        candidate_id: str,
        source_metadata_hash: str,
        request: PolicyRequest,
        correlation_id: str,
    ) -> McpInstallationPlan:
        """Create a package plan; this method never resolves or installs it."""

        decision = self._installation_decision(request)
        plan = McpInstallationPlanBuilder.for_package(
            manifest=manifest,
            package_index=package_index,
            verification=verification,
            capability_id=request.capability_id,
            candidate_id=candidate_id,
            source_metadata_hash=source_metadata_hash,
            policy_decision=decision,
        )
        self._publish_plan(plan, request=request, correlation_id=correlation_id)
        return plan

    def plan_remote(
        self,
        *,
        manifest: McpServerManifest,
        remote_index: int,
        verification: McpRemoteEndpointVerification,
        candidate_id: str,
        source_metadata_hash: str,
        request: PolicyRequest,
        correlation_id: str,
    ) -> McpInstallationPlan:
        """Create a remote endpoint plan; this method never connects to it."""

        decision = self._installation_decision(request)
        plan = McpInstallationPlanBuilder.for_remote(
            manifest=manifest,
            remote_index=remote_index,
            verification=verification,
            capability_id=request.capability_id,
            candidate_id=candidate_id,
            source_metadata_hash=source_metadata_hash,
            policy_decision=decision,
        )
        self._publish_plan(plan, request=request, correlation_id=correlation_id)
        return plan

    def _installation_decision(self, request: PolicyRequest) -> PolicyDecision:
        if request.action is not PolicyAction.INSTALL:
            raise ValueError("MCP installation planning requires the install policy action")
        # Package installation and remote-origin registration both need an
        # isolated execution context, even when a broad policy rule says ALLOW.
        if not request.sandboxed:
            raise McpInstallationBlocked("sandbox-baseline-required")
        decision = self._policy_engine.decide(request)
        if decision.kind is PolicyDecisionKind.DENY:
            raise McpInstallationBlocked(decision.reason_code, decision)
        if decision.kind is PolicyDecisionKind.REQUIRE_SANDBOX and not request.sandboxed:
            raise McpInstallationBlocked("sandbox-required", decision)
        return decision

    def _publish_plan(
        self,
        plan: McpInstallationPlan,
        *,
        request: PolicyRequest,
        correlation_id: str,
    ) -> None:
        """Publish an audit-safe projection that excludes secrets and arguments."""

        self._events.publish(
            new_event(
                event_type="mcp.install_plan.created.v1",
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                subject_id=plan.capability_id,
                correlation_id=correlation_id,
                payload={
                    "plan_id": plan.plan_id,
                    "candidate_id": plan.candidate_id,
                    "server_name": plan.server_name,
                    "target": plan.target.value,
                    "transport": plan.transport.value,
                    "readiness": plan.readiness.value,
                    "review_reasons": plan.review_reasons,
                    "required_controls": plan.required_controls,
                    "static_finding_codes": tuple(finding.code for finding in plan.static_findings),
                    "secret_binding_required": bool(plan.secret_variable_names),
                    "unconsumed_argument_kinds": plan.unconsumed_argument_kinds,
                    "policy": {
                        "decision": plan.policy_decision.kind.value,
                        "reason_code": plan.policy_decision.reason_code,
                        "policy_version": plan.policy_decision.policy_version,
                        "rule_id": plan.policy_decision.rule_id,
                    },
                    "artifact": {
                        "kind": plan.target_reference.kind,
                        "locator": plan.target_reference.locator,
                        "version": plan.target_reference.version,
                        "digest": plan.target_reference.digest,
                    },
                },
            )
        )
