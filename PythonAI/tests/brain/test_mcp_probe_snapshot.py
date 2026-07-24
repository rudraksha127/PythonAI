from __future__ import annotations

from datetime import timedelta
import unittest

from src.brain.adapters.in_memory import (
    DeclarativePolicyRule,
    DefaultDenyPolicyEngine,
    InMemoryEventPublisher,
)
from src.brain.application.mcp_installation import McpInstallationPlanningService
from src.brain.application.mcp_probe import McpProbeSnapshotService
from src.brain.domain.models import (
    PolicyAction,
    PolicyDecisionKind,
    PolicyRequest,
    RiskLevel,
    TrustTier,
    utc_now,
)
from src.brain.mcp.installation import McpInstallationPlan, McpPackageArtifactVerification
from src.brain.mcp.probe import (
    McpProbeExecutionEvidence,
    McpProbeSnapshotBuilder,
    McpProbeTranscript,
    McpProbeValidationError,
    McpPromptDescriptor,
    McpResourceDescriptor,
    McpToolDescriptor,
)
from src.brain.mcp.server_manifest import McpTransportType, parse_server_manifest


SHA256_A = "sha256:" + "a" * 64


def ready_plan() -> tuple[McpInstallationPlan, InMemoryEventPublisher]:
    events = InMemoryEventPublisher()
    policy = DefaultDenyPolicyEngine(
        [
            DeclarativePolicyRule(
                rule_id="allow-install",
                effect=PolicyDecisionKind.ALLOW,
                actions=frozenset({PolicyAction.INSTALL}),
                requires_sandbox=True,
            )
        ]
    )
    installer = McpInstallationPlanningService(policy, events)
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
    request = PolicyRequest(
        action=PolicyAction.INSTALL,
        principal_id="system",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        capability_id="mcp.io.forgeai/example",
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
        sandboxed=True,
    )
    return (
        installer.plan_package(
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
            candidate_id="candidate:example",
            source_metadata_hash=SHA256_A,
            request=request,
            correlation_id="corr-install-plan",
        ),
        events,
    )


def transcript(*, credential_free: bool = True, server_name: str = "io.forgeai/example") -> McpProbeTranscript:
    started = utc_now()
    return McpProbeTranscript(
        server_name=server_name,
        protocol_version="2025-11-25",
        transport=McpTransportType.STDIO,
        execution=McpProbeExecutionEvidence(
            probe_id="probe:example",
            isolated_runtime_id="sandbox:example",
            credential_free=credential_free,
            started_at=started,
            completed_at=started + timedelta(seconds=1),
        ),
        tools=(
            McpToolDescriptor(
                name="search_docs",
                description="Search approved documentation.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                output_schema={"type": "object"},
            ),
        ),
        resources=(
            McpResourceDescriptor(
                uri="forgeai://docs/index", name="Documentation index", mime_type="application/json"
            ),
        ),
        prompts=(McpPromptDescriptor(name="research", description="Research an approved source."),),
        tools_listed=True,
        resources_listed=True,
        prompts_listed=True,
    )


class McpProbeSnapshotTests(unittest.TestCase):
    def test_credential_free_full_probe_creates_immutable_tool_snapshot_and_safe_event(self) -> None:
        plan, events = ready_plan()
        service = McpProbeSnapshotService(events)

        snapshot = service.validate_and_snapshot(
            plan=plan,
            transcript=transcript(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="corr-probe",
        )

        self.assertTrue(snapshot.snapshot_hash.startswith("sha256:"))
        self.assertEqual("search_docs", snapshot.tools[0].name)
        self.assertEqual(1, len(snapshot.resources))
        self.assertEqual(1, len(snapshot.prompts))
        event = events.events()[-1]
        self.assertEqual("mcp.tool_snapshot.created.v1", event.event_type)
        self.assertEqual(("search_docs",), event.payload["tool_names"])
        self.assertNotIn("input_schema", str(dict(event.payload)))

    def test_probe_must_be_credential_free_and_match_the_plan_identity(self) -> None:
        plan, _ = ready_plan()

        with self.assertRaises(McpProbeValidationError):
            McpProbeSnapshotBuilder.from_transcript(
                plan=plan,
                transcript=transcript(credential_free=False),
            )
        with self.assertRaises(McpProbeValidationError):
            McpProbeSnapshotBuilder.from_transcript(
                plan=plan,
                transcript=transcript(server_name="unexpected-server"),
            )

    def test_external_json_schema_references_are_rejected_without_fetching_them(self) -> None:
        with self.assertRaises(McpProbeValidationError):
            McpToolDescriptor(
                name="unsafe_schema",
                description=None,
                input_schema={"$ref": "https://untrusted.example.test/schema.json"},
            )

    def test_all_metadata_list_calls_must_complete_before_registration(self) -> None:
        plan, _ = ready_plan()
        complete = transcript()
        incomplete = McpProbeTranscript(
            server_name=complete.server_name,
            protocol_version=complete.protocol_version,
            transport=complete.transport,
            execution=complete.execution,
            tools=complete.tools,
            resources=(),
            prompts=(),
            tools_listed=True,
            resources_listed=False,
            prompts_listed=False,
        )

        with self.assertRaises(McpProbeValidationError):
            McpProbeSnapshotBuilder.from_transcript(plan=plan, transcript=incomplete)

