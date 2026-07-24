"""Application service for read-only MCP artifact resolution and verification."""

from __future__ import annotations

from typing import Protocol

from ..domain.events import new_event
from ..mcp.artifact import (
    McpArtifactTrustProfile,
    McpArtifactVerificationReport,
    McpArtifactVerifier,
    McpResolvedPackageArtifact,
)
from ..mcp.server_manifest import McpPackageSpec, McpServerManifest
from .ports import EventPublisherPort


class McpArtifactResolverPort(Protocol):
    """A registry-specific, read-only adapter that returns resolved package metadata."""

    def resolve(self, package: McpPackageSpec) -> McpResolvedPackageArtifact:
        """Resolve exact artifact metadata; do not download or install package code."""


class McpArtifactResolutionService:
    """Resolve one selected package, verify it, and publish only a safe evidence summary."""

    def __init__(self, resolver: McpArtifactResolverPort, events: EventPublisherPort) -> None:
        self._resolver = resolver
        self._events = events

    def resolve_and_verify(
        self,
        *,
        manifest: McpServerManifest,
        package_index: int,
        profile: McpArtifactTrustProfile,
        tenant_id: str,
        workspace_id: str,
        correlation_id: str,
    ) -> McpArtifactVerificationReport:
        """Perform read-only metadata resolution; caller still needs install policy approval."""

        if not 0 <= package_index < len(manifest.packages):
            raise ValueError("package_index does not select a declared package")
        package = manifest.packages[package_index]
        artifact = self._resolver.resolve(package)
        report = McpArtifactVerifier.verify(package, artifact, profile)
        self._events.publish(
            new_event(
                event_type="mcp.artifact.verified.v1",
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                subject_id=manifest.server_name,
                correlation_id=correlation_id,
                payload={
                    "registry_type": artifact.registry_type,
                    "identifier": artifact.identifier,
                    "version": artifact.version,
                    "evidence_id": artifact.evidence_id,
                    "artifact_digest": artifact.artifact_digest,
                    "sbom_digest": artifact.sbom_digest,
                    "provenance_verified": artifact.provenance_verified,
                    "license_count": len(artifact.licenses),
                    "vulnerability_count": len(artifact.vulnerabilities),
                    "ready_for_install_planning": report.ready_for_install_planning,
                    "finding_codes": tuple(finding.code for finding in report.findings),
                },
            )
        )
        return report
