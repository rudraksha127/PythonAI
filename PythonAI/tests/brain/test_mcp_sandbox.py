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
from src.brain.application.mcp_sandbox import McpSandboxedProbeService
from src.brain.domain.models import (
    PolicyAction,
    PolicyDecisionKind,
    PolicyRequest,
    RiskLevel,
    TrustTier,
    utc_now,
)
from src.brain.mcp.installation import (
    McpInstallationPlan,
    McpPackageArtifactVerification,
    McpRemoteEndpointVerification,
)
from src.brain.mcp.probe import McpProbeExecutionEvidence, McpProbeTranscript, McpToolDescriptor
from src.brain.mcp.sandbox import (
    McpProbeSandboxProfile,
    McpProbeSandboxProfileFactory,
    McpSandboxNetworkMode,
    McpSandboxProfileError,
)
from src.brain.mcp.server_manifest import McpTransportType, parse_server_manifest


SHA256_A = "sha256:" + "a" * 64


def install_request() -> PolicyRequest:
    return PolicyRequest(
        action=PolicyAction.INSTALL,
        principal_id="forgeai-system",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        capability_id="mcp.io.forgeai/example",
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
        sandboxed=True,
    )


def planning_service(events: InMemoryEventPublisher) -> McpInstallationPlanningService:
    policy = DefaultDenyPolicyEngine(
        [
            DeclarativePolicyRule(
                rule_id="allow-sandboxed-install",
                effect=PolicyDecisionKind.ALLOW,
                actions=frozenset({PolicyAction.INSTALL}),
                requires_sandbox=True,
            )
        ]
    )
    return McpInstallationPlanningService(policy, events)


def ready_package_plan(events: InMemoryEventPublisher) -> McpInstallationPlan:
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
    return planning_service(events).plan_package(
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
        request=install_request(),
        correlation_id="corr-plan",
    )


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[McpInstallationPlan, McpProbeSandboxProfile]] = []

    def probe(
        self,
        *,
        plan: McpInstallationPlan,
        profile: McpProbeSandboxProfile,
    ) -> McpProbeTranscript:
        self.calls.append((plan, profile))
        started = utc_now()
        return McpProbeTranscript(
            server_name=plan.server_name,
            protocol_version="2025-11-25",
            transport=plan.transport,
            execution=McpProbeExecutionEvidence(
                probe_id="probe:sandboxed",
                isolated_runtime_id="sandbox:test",
                credential_free=True,
                started_at=started,
                completed_at=started + timedelta(seconds=1),
            ),
            tools=(McpToolDescriptor(name="search", description=None, input_schema={"type": "object"}),),
            resources=(),
            prompts=(),
            tools_listed=True,
            resources_listed=True,
            prompts_listed=True,
        )


class FailingRunner:
    def probe(self, **_: object) -> McpProbeTranscript:
        raise RuntimeError("sandbox runner rejected the target")


class McpSandboxTests(unittest.TestCase):
    def test_package_probe_profile_has_no_network_host_filesystem_or_credentials(self) -> None:
        plan = ready_package_plan(InMemoryEventPublisher())

        profile = McpProbeSandboxProfileFactory.for_plan(plan)

        self.assertEqual(McpSandboxNetworkMode.NONE, profile.network_mode)
        self.assertEqual((), profile.allowed_origins)
        self.assertTrue(profile.read_only_root_filesystem)
        self.assertFalse(profile.host_filesystem_access)
        self.assertFalse(profile.credential_injection)
        self.assertFalse(profile.privilege_escalation)

    def test_remote_profile_scopes_egress_to_exact_https_origin(self) -> None:
        events = InMemoryEventPublisher()
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/remote",
                "version": "1.0.0",
                "remotes": [
                    {"type": "streamable-http", "url": "https://REMOTE.example.test:8443/mcp"}
                ],
            }
        )
        plan = planning_service(events).plan_remote(
            manifest=manifest,
            remote_index=0,
            verification=McpRemoteEndpointVerification(
                url="https://REMOTE.example.test:8443/mcp",
                transport=McpTransportType.STREAMABLE_HTTP,
                evidence_id="endpoint:example",
                tls_identity_verified=True,
            ),
            candidate_id="candidate:remote",
            source_metadata_hash=SHA256_A,
            request=install_request(),
            correlation_id="corr-remote",
        )

        profile = McpProbeSandboxProfileFactory.for_plan(plan)

        self.assertTrue(plan.ready_for_sandbox_execution)
        self.assertEqual(McpSandboxNetworkMode.ORIGIN_ALLOWLIST, profile.network_mode)
        self.assertEqual(("https://remote.example.test:8443",), profile.allowed_origins)

    def test_service_runs_only_through_profiled_runner_then_validates_snapshot(self) -> None:
        events = InMemoryEventPublisher()
        plan = ready_package_plan(events)
        runner = RecordingRunner()
        service = McpSandboxedProbeService(runner, McpProbeSnapshotService(events), events)

        snapshot = service.probe_and_snapshot(
            plan=plan,
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="corr-sandbox",
        )

        self.assertEqual("search", snapshot.tools[0].name)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(McpSandboxNetworkMode.NONE, runner.calls[0][1].network_mode)
        self.assertEqual(
            ["mcp.install_plan.created.v1", "mcp.probe.started.v1", "mcp.tool_snapshot.created.v1"],
            [event.event_type for event in events.events()],
        )

    def test_failed_runner_is_audited_and_pending_review_plan_is_never_sent_to_it(self) -> None:
        events = InMemoryEventPublisher()
        plan = ready_package_plan(events)
        service = McpSandboxedProbeService(FailingRunner(), McpProbeSnapshotService(events), events)

        with self.assertRaises(RuntimeError):
            service.probe_and_snapshot(
                plan=plan,
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="corr-failure",
            )
        self.assertEqual("mcp.probe.failed.v1", events.events()[-1].event_type)

        incomplete = planning_service(InMemoryEventPublisher()).plan_package(
            manifest=parse_server_manifest(
                {
                    "name": "io.forgeai/incomplete",
                    "packages": [
                        {
                            "registryType": "pypi",
                            "identifier": "incomplete-mcp",
                            "transport": {"type": "stdio"},
                        }
                    ],
                }
            ),
            package_index=0,
            verification=McpPackageArtifactVerification(
                registry_type="pypi",
                identifier="incomplete-mcp",
                version="1.0.0",
                evidence_id="scan:incomplete",
                artifact_digest=None,
                provenance_verified=False,
            ),
            candidate_id="candidate:incomplete",
            source_metadata_hash=SHA256_A,
            request=install_request(),
            correlation_id="corr-incomplete",
        )
        with self.assertRaises(McpSandboxProfileError):
            McpProbeSandboxProfileFactory.for_plan(incomplete)

