"""Orchestrate a sandboxed MCP probe through an injected runtime implementation."""

from __future__ import annotations

from typing import Protocol

from ..domain.events import new_event
from ..mcp.installation import McpInstallationPlan
from ..mcp.probe import McpProbeTranscript, McpToolCatalogSnapshot
from ..mcp.sandbox import McpProbeSandboxProfile, McpProbeSandboxProfileFactory
from .mcp_probe import McpProbeSnapshotService
from .ports import EventPublisherPort


class McpSandboxProbeRunnerPort(Protocol):
    """A hardened OCI/microVM/OS runner that performs exactly one MCP probe."""

    def probe(
        self,
        *,
        plan: McpInstallationPlan,
        profile: McpProbeSandboxProfile,
    ) -> McpProbeTranscript:
        """Run the already-installed target under the supplied profile and return metadata only."""


class McpSandboxedProbeService:
    """Request a strict probe and hand only validated metadata to the catalog service."""

    def __init__(
        self,
        runner: McpSandboxProbeRunnerPort,
        snapshots: McpProbeSnapshotService,
        events: EventPublisherPort,
    ) -> None:
        self._runner = runner
        self._snapshots = snapshots
        self._events = events

    def probe_and_snapshot(
        self,
        *,
        plan: McpInstallationPlan,
        tenant_id: str,
        workspace_id: str,
        correlation_id: str,
    ) -> McpToolCatalogSnapshot:
        """Run an injected sandbox probe; activation remains a separate lifecycle action."""

        profile = McpProbeSandboxProfileFactory.for_plan(plan)
        self._events.publish(
            new_event(
                event_type="mcp.probe.started.v1",
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                subject_id=plan.capability_id,
                correlation_id=correlation_id,
                payload={
                    "plan_id": plan.plan_id,
                    "target": plan.target.value,
                    "network_mode": profile.network_mode.value,
                    "allowed_origins": profile.allowed_origins,
                    "maximum_runtime_seconds": profile.maximum_runtime_seconds,
                    "maximum_memory_megabytes": profile.maximum_memory_megabytes,
                    "maximum_processes": profile.maximum_processes,
                    "credential_injection": profile.credential_injection,
                },
            )
        )
        try:
            transcript = self._runner.probe(plan=plan, profile=profile)
            return self._snapshots.validate_and_snapshot(
                plan=plan,
                transcript=transcript,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                correlation_id=correlation_id,
            )
        except Exception as error:
            self._events.publish(
                new_event(
                    event_type="mcp.probe.failed.v1",
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    subject_id=plan.capability_id,
                    correlation_id=correlation_id,
                    payload={
                        "plan_id": plan.plan_id,
                        "error_type": type(error).__name__,
                    },
                )
            )
            raise
