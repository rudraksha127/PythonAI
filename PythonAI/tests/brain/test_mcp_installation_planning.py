from __future__ import annotations

import unittest

from src.brain.adapters.in_memory import (
    DeclarativePolicyRule,
    DefaultDenyPolicyEngine,
    InMemoryEventPublisher,
)
from src.brain.application.mcp_installation import (
    McpInstallationBlocked,
    McpInstallationPlanningService,
)
from src.brain.domain.models import (
    PolicyAction,
    PolicyDecisionKind,
    PolicyRequest,
    RiskLevel,
    TrustTier,
)
from src.brain.mcp.installation import (
    McpInstallReadiness,
    McpPackageArtifactVerification,
    McpRemoteEndpointVerification,
)
from src.brain.mcp.server_manifest import McpTransportType, parse_server_manifest


SHA256_A = "sha256:" + "a" * 64


def install_request(*, sandboxed: bool = True) -> PolicyRequest:
    return PolicyRequest(
        action=PolicyAction.INSTALL,
        principal_id="forgeai-system",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        capability_id="mcp.io.forgeai/example",
        risk_level=RiskLevel.MEDIUM,
        trust_tier=TrustTier.OFFICIAL,
        requested_permissions=frozenset({"network:egress:registry.example.test"}),
        automated=True,
        sandboxed=sandboxed,
    )


def allow_install_service() -> tuple[McpInstallationPlanningService, InMemoryEventPublisher]:
    events = InMemoryEventPublisher()
    policy = DefaultDenyPolicyEngine(
        [
            DeclarativePolicyRule(
                rule_id="allow-sandboxed-official-install",
                effect=PolicyDecisionKind.ALLOW,
                actions=frozenset({PolicyAction.INSTALL}),
                minimum_trust_tier=TrustTier.VERIFIED,
                maximum_risk_level=RiskLevel.HIGH,
                requires_sandbox=True,
            )
        ]
    )
    return McpInstallationPlanningService(policy, events), events


class McpInstallationPlanningTests(unittest.TestCase):
    def test_verified_package_becomes_a_sandbox_ready_plan_without_exposing_secrets(self) -> None:
        service, events = allow_install_service()
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/example",
                "version": "1.2.3",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "forgeai-example-mcp",
                        "version": "1.2.3",
                        "transport": {"type": "stdio"},
                        "environmentVariables": [
                            {"name": "EXAMPLE_API_KEY", "isRequired": True, "isSecret": True}
                        ],
                    }
                ],
            }
        )

        plan = service.plan_package(
            manifest=manifest,
            package_index=0,
            verification=McpPackageArtifactVerification(
                registry_type="pypi",
                identifier="forgeai-example-mcp",
                version="1.2.3",
                evidence_id="artifact-scan:123",
                artifact_digest=SHA256_A,
                sbom_digest=SHA256_A,
                provenance_verified=True,
            ),
            candidate_id="candidate:official:example",
            source_metadata_hash=SHA256_A,
            request=install_request(),
            correlation_id="corr-package-ready",
        )

        self.assertTrue(plan.ready_for_sandbox_execution)
        self.assertEqual(McpInstallReadiness.READY_FOR_SANDBOX, plan.readiness)
        self.assertEqual(("EXAMPLE_API_KEY",), plan.secret_variable_names)
        self.assertIn("credential-free-mcp-probe", plan.required_controls)
        self.assertEqual(SHA256_A, plan.target_reference.digest)
        event = events.events()[0]
        self.assertEqual("mcp.install_plan.created.v1", event.event_type)
        self.assertTrue(event.payload["secret_binding_required"])
        self.assertNotIn("EXAMPLE_API_KEY", str(dict(event.payload)))

    def test_missing_artifact_evidence_and_raw_arguments_prevent_automatic_install(self) -> None:
        service, _ = allow_install_service()
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/example",
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "@forgeai/example",
                        "transport": {"type": "stdio"},
                        "packageArguments": [{"type": "named", "name": "--registry"}],
                        "runtimeArguments": [{"type": "named", "name": "--unsafe-mode"}],
                    }
                ],
            }
        )

        plan = service.plan_package(
            manifest=manifest,
            package_index=0,
            verification=McpPackageArtifactVerification(
                registry_type="npm",
                identifier="@forgeai/example",
                version="4.5.6",
                evidence_id="artifact-scan:incomplete",
                artifact_digest=None,
                provenance_verified=False,
            ),
            candidate_id="candidate:community:example",
            source_metadata_hash=SHA256_A,
            request=install_request(),
            correlation_id="corr-package-review",
        )

        self.assertFalse(plan.ready_for_sandbox_execution)
        self.assertEqual(McpInstallReadiness.PENDING_REVIEW, plan.readiness)
        self.assertEqual(("package", "runtime"), plan.unconsumed_argument_kinds)
        self.assertTrue(
            {
                "artifact-digest-missing",
                "artifact-provenance-unverified",
                "package-arguments-require-approved-template",
                "runtime-arguments-require-approved-template",
            }.issubset(plan.review_reasons)
        )

    def test_remote_requires_https_streamable_http_and_identity_verification_before_auto_registration(self) -> None:
        service, _ = allow_install_service()
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/remote",
                "remotes": [{"type": "sse", "url": "http://remote.example.test/sse"}],
            }
        )

        plan = service.plan_remote(
            manifest=manifest,
            remote_index=0,
            verification=McpRemoteEndpointVerification(
                url="http://remote.example.test/sse",
                transport=McpTransportType.SSE,
                evidence_id="endpoint-check:123",
                tls_identity_verified=False,
            ),
            candidate_id="candidate:remote:example",
            source_metadata_hash=SHA256_A,
            request=install_request(),
            correlation_id="corr-remote-review",
        )

        self.assertFalse(plan.ready_for_sandbox_execution)
        self.assertTrue(
            {
                "remote-endpoint-not-https",
                "remote-transport-requires-compatibility-review",
                "remote-tls-identity-unverified",
                "remote-server-version-unpinned",
            }.issubset(plan.review_reasons)
        )

    def test_default_deny_and_unsandboxed_baseline_block_planning(self) -> None:
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/example",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "forgeai-example-mcp",
                        "transport": {"type": "stdio"},
                    }
                ],
            }
        )
        verification = McpPackageArtifactVerification(
            registry_type="pypi",
            identifier="forgeai-example-mcp",
            version="1.0.0",
            evidence_id="artifact-scan:123",
            artifact_digest=SHA256_A,
            provenance_verified=True,
        )
        default_deny = McpInstallationPlanningService(
            DefaultDenyPolicyEngine(), InMemoryEventPublisher()
        )
        with self.assertRaises(McpInstallationBlocked) as denied:
            default_deny.plan_package(
                manifest=manifest,
                package_index=0,
                verification=verification,
                candidate_id="candidate:untrusted:example",
                source_metadata_hash=SHA256_A,
                request=install_request(),
                correlation_id="corr-default-deny",
            )
        self.assertEqual("no-matching-policy-rule", denied.exception.reason_code)

        service, _ = allow_install_service()
        with self.assertRaises(McpInstallationBlocked) as unsandboxed:
            service.plan_package(
                manifest=manifest,
                package_index=0,
                verification=verification,
                candidate_id="candidate:official:example",
                source_metadata_hash=SHA256_A,
                request=install_request(sandboxed=False),
                correlation_id="corr-unsandboxed",
            )
        self.assertEqual("sandbox-baseline-required", unsandboxed.exception.reason_code)

    def test_policy_action_cannot_be_substituted_for_install_planning(self) -> None:
        service, _ = allow_install_service()
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/example",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "forgeai-example-mcp",
                        "transport": {"type": "stdio"},
                    }
                ],
            }
        )
        request = install_request()
        invalid_request = PolicyRequest(
            action=PolicyAction.EXECUTE,
            principal_id=request.principal_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            capability_id=request.capability_id,
            risk_level=request.risk_level,
            trust_tier=request.trust_tier,
            requested_permissions=request.requested_permissions,
            automated=request.automated,
            sandboxed=True,
        )
        with self.assertRaises(ValueError):
            service.plan_package(
                manifest=manifest,
                package_index=0,
                verification=McpPackageArtifactVerification(
                    registry_type="pypi",
                    identifier="forgeai-example-mcp",
                    version="1.0.0",
                    evidence_id="artifact-scan:123",
                    artifact_digest=SHA256_A,
                    provenance_verified=True,
                ),
                candidate_id="candidate:official:example",
                source_metadata_hash=SHA256_A,
                request=invalid_request,
                correlation_id="corr-wrong-action",
            )

