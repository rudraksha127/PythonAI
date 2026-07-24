"""Application boundary for accepting validated, credential-free MCP probes."""

from __future__ import annotations

from ..domain.events import new_event
from ..mcp.installation import McpInstallationPlan
from ..mcp.probe import McpProbeSnapshotBuilder, McpProbeTranscript, McpToolCatalogSnapshot
from .ports import EventPublisherPort


class McpProbeSnapshotService:
    """Create an audit-safe immutable catalog snapshot from a probe transcript."""

    def __init__(self, events: EventPublisherPort) -> None:
        self._events = events

    def validate_and_snapshot(
        self,
        *,
        plan: McpInstallationPlan,
        transcript: McpProbeTranscript,
        tenant_id: str,
        workspace_id: str,
        correlation_id: str,
    ) -> McpToolCatalogSnapshot:
        """Validate metadata and publish a summary; this never activates a server."""

        snapshot = McpProbeSnapshotBuilder.from_transcript(plan=plan, transcript=transcript)
        self._events.publish(
            new_event(
                event_type="mcp.tool_snapshot.created.v1",
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                subject_id=plan.capability_id,
                correlation_id=correlation_id,
                payload={
                    "snapshot_id": snapshot.snapshot_id,
                    "snapshot_hash": snapshot.snapshot_hash,
                    "plan_id": snapshot.plan_id,
                    "server_name": snapshot.server_name,
                    "protocol_version": snapshot.protocol_version,
                    "transport": snapshot.transport.value,
                    "tool_count": len(snapshot.tools),
                    "tool_names": tuple(tool.name for tool in snapshot.tools),
                    "resource_count": len(snapshot.resources),
                    "prompt_count": len(snapshot.prompts),
                    "target": {
                        "kind": snapshot.target_reference.kind,
                        "locator": snapshot.target_reference.locator,
                        "version": snapshot.target_reference.version,
                        "digest": snapshot.target_reference.digest,
                    },
                },
            )
        )
        return snapshot
