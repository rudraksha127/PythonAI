from __future__ import annotations

import unittest

from src.brain.adapters.in_memory import InMemoryEventPublisher
from src.brain.application.mcp_artifact import McpArtifactResolutionService
from src.brain.domain.models import PolicyDecision, PolicyDecisionKind
from src.brain.mcp.artifact import (
    ArtifactVulnerabilitySeverity,
    McpArtifactTrustProfile,
    McpArtifactVerificationError,
    McpArtifactVerifier,
    McpArtifactVulnerability,
    McpResolvedPackageArtifact,
)
from src.brain.mcp.installation import McpInstallationPlanBuilder
from src.brain.mcp.server_manifest import parse_server_manifest


SHA256_A = "sha256:" + "a" * 64


def manifest(*, pinned: bool = True):
    package: dict[str, object] = {
        "registryType": "pypi",
        "identifier": "forgeai-example-mcp",
        "transport": {"type": "stdio"},
    }
    if pinned:
        package["version"] = "1.2.3"
    return parse_server_manifest({"name": "io.forgeai/example", "packages": [package]})


def artifact(**overrides) -> McpResolvedPackageArtifact:
    values = {
        "registry_type": "pypi",
        "identifier": "forgeai-example-mcp",
        "version": "1.2.3",
        "evidence_id": "registry-scan:example",
        "artifact_url": "https://files.pythonhosted.org/packages/example.whl",
        "artifact_digest": SHA256_A,
        "sbom_digest": SHA256_A,
        "provenance_verified": True,
        "provenance_reference": "attestation:example",
        "licenses": ("MIT",),
        "vulnerabilities": (McpArtifactVulnerability("CVE-low", ArtifactVulnerabilitySeverity.LOW),),
    }
    values.update(overrides)
    return McpResolvedPackageArtifact(**values)


def profile() -> McpArtifactTrustProfile:
    return McpArtifactTrustProfile(
        allowed_artifact_hosts=frozenset({"files.pythonhosted.org"}),
        maximum_vulnerability_severity=ArtifactVulnerabilitySeverity.MEDIUM,
    )


class FakeResolver:
    def __init__(self, resolved: McpResolvedPackageArtifact) -> None:
        self.resolved = resolved
        self.calls = []

    def resolve(self, package):
        self.calls.append(package)
        return self.resolved


class McpArtifactVerificationTests(unittest.TestCase):
    def test_read_only_resolve_verifies_complete_evidence_and_feeds_installation_planner(self) -> None:
        events = InMemoryEventPublisher()
        resolver = FakeResolver(artifact())
        source_manifest = manifest()
        report = McpArtifactResolutionService(resolver, events).resolve_and_verify(
            manifest=source_manifest,
            package_index=0,
            profile=profile(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="corr-artifact",
        )

        self.assertTrue(report.ready_for_install_planning)
        self.assertEqual((), report.findings)
        self.assertEqual("mcp.artifact.verified.v1", events.events()[0].event_type)
        self.assertTrue(events.events()[0].payload["ready_for_install_planning"])
        plan = McpInstallationPlanBuilder.for_package(
            manifest=source_manifest,
            package_index=0,
            verification=report.verification,
            capability_id="mcp.io.forgeai/example",
            candidate_id="candidate:example",
            source_metadata_hash=SHA256_A,
            policy_decision=PolicyDecision(
                kind=PolicyDecisionKind.ALLOW,
                reason_code="test-allow",
                policy_version="test-v1",
            ),
        )
        self.assertTrue(plan.ready_for_sandbox_execution)
        self.assertEqual(1, len(resolver.calls))

    def test_missing_evidence_untrusted_host_and_high_vulnerability_block_install_planning(self) -> None:
        source_manifest = manifest()
        report = McpArtifactVerifier.verify(
            source_manifest.packages[0],
            artifact(
                artifact_url="http://untrusted.example.test/example.whl",
                artifact_digest=None,
                sbom_digest=None,
                provenance_verified=False,
                licenses=(),
                vulnerabilities=(
                    McpArtifactVulnerability("CVE-high", ArtifactVulnerabilitySeverity.HIGH),
                ),
            ),
            profile(),
        )

        self.assertFalse(report.ready_for_install_planning)
        self.assertTrue(
            {
                "artifact-url-not-https",
                "artifact-host-not-allowlisted",
                "artifact-digest-missing",
                "sbom-missing",
                "artifact-provenance-unverified",
                "license-metadata-missing",
                "vulnerability-severity-exceeds-threshold",
            }.issubset({finding.code for finding in report.findings})
        )

    def test_identity_mismatch_is_rejected_before_a_report_can_be_created(self) -> None:
        source_manifest = manifest()
        with self.assertRaises(McpArtifactVerificationError):
            McpArtifactVerifier.verify(
                source_manifest.packages[0],
                artifact(identifier="dependency-confusion-package"),
                profile(),
            )

    def test_resolved_version_pins_an_unpinned_manifest_package_for_later_planning(self) -> None:
        source_manifest = manifest(pinned=False)
        report = McpArtifactVerifier.verify(source_manifest.packages[0], artifact(), profile())

        self.assertTrue(report.ready_for_install_planning)
        self.assertEqual("1.2.3", report.verification.version)
        self.assertEqual(SHA256_A, report.verification.artifact_digest)

