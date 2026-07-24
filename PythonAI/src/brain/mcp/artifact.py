"""Supply-chain evidence and verification for MCP package artifacts.

This module never downloads a package. A registry-specific resolver supplies
metadata; ForgeAI verifies identity, allowed origin, immutable digest, SBOM,
provenance, license, and vulnerability posture before the installation planner
can treat it as usable evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Iterable
from urllib.parse import urlparse

from ..domain.models import utc_now
from .installation import McpPackageArtifactVerification
from .server_manifest import McpPackageSpec


class McpArtifactVerificationError(ValueError):
    """Raised when a resolver result does not identify the selected package exactly."""


class ArtifactVulnerabilitySeverity(IntEnum):
    """Ordered severity used by a deterministic admission threshold."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    UNKNOWN = 5


def _text(field_name: str, value: str, *, maximum: int = 4_096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpArtifactVerificationError(f"{field_name} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum:
        raise McpArtifactVerificationError(f"{field_name} exceeds the maximum length")
    return result


@dataclass(frozen=True, slots=True)
class McpArtifactVulnerability:
    """A normalized scanner finding; raw scanner output belongs in evidence storage."""

    identifier: str
    severity: ArtifactVulnerabilitySeverity
    fixed_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _text("vulnerability.identifier", self.identifier, maximum=512))
        if not isinstance(self.severity, ArtifactVulnerabilitySeverity):
            raise McpArtifactVerificationError("vulnerability.severity must be a known severity")
        if self.fixed_version is not None:
            object.__setattr__(
                self,
                "fixed_version",
                _text("vulnerability.fixed_version", self.fixed_version, maximum=256),
            )


@dataclass(frozen=True, slots=True)
class McpResolvedPackageArtifact:
    """Resolved immutable package evidence from one registry adapter or scanner pipeline."""

    registry_type: str
    identifier: str
    version: str
    evidence_id: str
    artifact_url: str
    artifact_digest: str | None
    sbom_digest: str | None
    provenance_verified: bool
    provenance_reference: str | None = None
    licenses: tuple[str, ...] = ()
    vulnerabilities: tuple[McpArtifactVulnerability, ...] = ()
    resolved_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_type", _text("artifact.registry_type", self.registry_type, maximum=256))
        object.__setattr__(self, "identifier", _text("artifact.identifier", self.identifier, maximum=512))
        object.__setattr__(self, "version", _text("artifact.version", self.version, maximum=256))
        object.__setattr__(self, "evidence_id", _text("artifact.evidence_id", self.evidence_id, maximum=512))
        object.__setattr__(self, "artifact_url", _text("artifact.artifact_url", self.artifact_url))
        parsed = urlparse(self.artifact_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise McpArtifactVerificationError("artifact.artifact_url must be an absolute HTTP(S) URL")
        if not isinstance(self.provenance_verified, bool):
            raise McpArtifactVerificationError("artifact.provenance_verified must be a boolean")
        if self.provenance_reference is not None:
            object.__setattr__(
                self,
                "provenance_reference",
                _text("artifact.provenance_reference", self.provenance_reference, maximum=2_048),
            )
        object.__setattr__(self, "licenses", tuple(sorted({_text("artifact.license", item, maximum=256) for item in self.licenses})))
        object.__setattr__(self, "vulnerabilities", tuple(self.vulnerabilities))
        if any(not isinstance(item, McpArtifactVulnerability) for item in self.vulnerabilities):
            raise McpArtifactVerificationError("artifact.vulnerabilities must contain normalized findings")
        if self.resolved_at.tzinfo is None:
            raise McpArtifactVerificationError("artifact.resolved_at must be timezone-aware")
        try:
            McpPackageArtifactVerification(
                registry_type=self.registry_type,
                identifier=self.identifier,
                version=self.version,
                evidence_id=self.evidence_id,
                artifact_digest=self.artifact_digest,
                provenance_verified=self.provenance_verified,
                sbom_digest=self.sbom_digest,
            )
        except ValueError as error:
            raise McpArtifactVerificationError("artifact digests must use immutable sha256 references") from error

    def to_installation_verification(self) -> McpPackageArtifactVerification:
        """Project evidence into the planner contract without exposing URL or raw scan data."""

        return McpPackageArtifactVerification(
            registry_type=self.registry_type,
            identifier=self.identifier,
            version=self.version,
            evidence_id=self.evidence_id,
            artifact_digest=self.artifact_digest,
            provenance_verified=self.provenance_verified,
            sbom_digest=self.sbom_digest,
        )


@dataclass(frozen=True, slots=True)
class McpArtifactTrustProfile:
    """Fail-closed local admission requirements for a selected package registry origin."""

    allowed_artifact_hosts: frozenset[str]
    maximum_vulnerability_severity: ArtifactVulnerabilitySeverity = ArtifactVulnerabilitySeverity.MEDIUM
    require_sbom: bool = True
    require_provenance: bool = True
    require_license: bool = True

    def __post_init__(self) -> None:
        normalized = frozenset(
            _text("trust.allowed_artifact_host", host, maximum=256).lower()
            for host in self.allowed_artifact_hosts
        )
        if not normalized:
            raise McpArtifactVerificationError("trust.allowed_artifact_hosts must not be empty")
        if any("/" in host or ":" in host or "@" in host for host in normalized):
            raise McpArtifactVerificationError("trust.allowed_artifact_hosts must contain hostnames only")
        object.__setattr__(self, "allowed_artifact_hosts", normalized)
        if not isinstance(self.maximum_vulnerability_severity, ArtifactVulnerabilitySeverity):
            raise McpArtifactVerificationError("trust.maximum_vulnerability_severity must be a known severity")
        for field_name in ("require_sbom", "require_provenance", "require_license"):
            if not isinstance(getattr(self, field_name), bool):
                raise McpArtifactVerificationError(f"trust.{field_name} must be a boolean")


@dataclass(frozen=True, slots=True)
class McpArtifactFinding:
    """A non-secret, explainable result of static supply-chain admission checks."""

    code: str
    blocking: bool
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text("finding.code", self.code, maximum=256))
        if not isinstance(self.blocking, bool):
            raise McpArtifactVerificationError("finding.blocking must be a boolean")
        object.__setattr__(self, "detail", _text("finding.detail", self.detail))


@dataclass(frozen=True, slots=True)
class McpArtifactVerificationReport:
    """Static verification outcome that feeds, but never bypasses, installation policy."""

    artifact: McpResolvedPackageArtifact
    verification: McpPackageArtifactVerification
    findings: tuple[McpArtifactFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, McpResolvedPackageArtifact):
            raise McpArtifactVerificationError("report.artifact must be a resolved package artifact")
        if not isinstance(self.verification, McpPackageArtifactVerification):
            raise McpArtifactVerificationError("report.verification must be installation verification evidence")
        object.__setattr__(self, "findings", tuple(self.findings))
        if any(not isinstance(finding, McpArtifactFinding) for finding in self.findings):
            raise McpArtifactVerificationError("report.findings must contain supply-chain findings")

    @property
    def ready_for_install_planning(self) -> bool:
        """True only when static evidence has no blocking gaps; policy is still required."""

        return not any(finding.blocking for finding in self.findings)


class McpArtifactVerifier:
    """Pure supply-chain verifier shared by PyPI/npm/OCI/NuGet resolver plugins."""

    @staticmethod
    def verify(
        package: McpPackageSpec,
        artifact: McpResolvedPackageArtifact,
        profile: McpArtifactTrustProfile,
    ) -> McpArtifactVerificationReport:
        """Check exact package identity and emit all safe-to-report admission findings."""

        if artifact.registry_type != package.registry_type:
            raise McpArtifactVerificationError("resolved artifact registry type does not match the selected package")
        if artifact.identifier != package.identifier:
            raise McpArtifactVerificationError("resolved artifact identifier does not match the selected package")
        if package.version is not None and artifact.version != package.version:
            raise McpArtifactVerificationError("resolved artifact version does not match the selected package")

        findings: list[McpArtifactFinding] = []
        parsed = urlparse(artifact.artifact_url)
        if parsed.scheme != "https":
            findings.append(
                McpArtifactFinding(
                    code="artifact-url-not-https",
                    blocking=True,
                    detail="Artifact retrieval URL must use HTTPS.",
                )
            )
        if parsed.username or parsed.password:
            findings.append(
                McpArtifactFinding(
                    code="artifact-url-contains-userinfo",
                    blocking=True,
                    detail="Artifact retrieval URL must not contain embedded credentials.",
                )
            )
        host = parsed.hostname.lower() if parsed.hostname else ""
        if host not in profile.allowed_artifact_hosts:
            findings.append(
                McpArtifactFinding(
                    code="artifact-host-not-allowlisted",
                    blocking=True,
                    detail="Artifact retrieval host is not in the trust profile allowlist.",
                )
            )
        if artifact.artifact_digest is None:
            findings.append(
                McpArtifactFinding(
                    code="artifact-digest-missing",
                    blocking=True,
                    detail="An immutable artifact digest is required before installation planning.",
                )
            )
        if profile.require_sbom and artifact.sbom_digest is None:
            findings.append(
                McpArtifactFinding(
                    code="sbom-missing",
                    blocking=True,
                    detail="The trust profile requires an SBOM digest.",
                )
            )
        if profile.require_provenance and not artifact.provenance_verified:
            findings.append(
                McpArtifactFinding(
                    code="artifact-provenance-unverified",
                    blocking=True,
                    detail="The trust profile requires verified package provenance.",
                )
            )
        if profile.require_license and not artifact.licenses:
            findings.append(
                McpArtifactFinding(
                    code="license-metadata-missing",
                    blocking=True,
                    detail="The trust profile requires at least one normalized license identifier.",
                )
            )
        for vulnerability in artifact.vulnerabilities:
            if vulnerability.severity > profile.maximum_vulnerability_severity:
                findings.append(
                    McpArtifactFinding(
                        code="vulnerability-severity-exceeds-threshold",
                        blocking=True,
                        detail=(
                            f"{vulnerability.identifier} severity {vulnerability.severity.name.lower()} "
                            "exceeds the configured admission threshold."
                        ),
                    )
                )
        return McpArtifactVerificationReport(
            artifact=artifact,
            verification=artifact.to_installation_verification(),
            findings=tuple(findings),
        )
