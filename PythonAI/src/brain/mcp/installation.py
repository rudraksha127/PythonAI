"""Non-executing, policy-gated installation plans for MCP servers.

Registry ``server.json`` documents describe *possible* launch mechanisms. They
are not launch instructions. This module turns a selected, independently
verified package or remote endpoint into an immutable plan that a later
sandboxed worker may consume. It deliberately contains no package-manager,
subprocess, network, secret, or MCP-client code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import Iterable
from urllib.parse import urlparse
from uuid import uuid4

from ..domain.models import ArtifactReference, PolicyDecision, PolicyDecisionKind, utc_now
from .server_manifest import (
    McpPackageSpec,
    McpRemoteSpec,
    McpServerManifest,
    McpStaticRiskFinding,
    McpTransportType,
)


_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)


class McpInstallationPlanningError(ValueError):
    """Raised when untrusted metadata cannot form an internally consistent plan."""


class McpInstallTarget(str, Enum):
    """The two installation targets supported by an MCP server document."""

    PACKAGE = "package"
    REMOTE = "remote"


class McpInstallReadiness(str, Enum):
    """Whether a plan may be handed to a sandboxed installation worker."""

    READY_FOR_SANDBOX = "ready-for-sandbox"
    PENDING_REVIEW = "pending-review"


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpInstallationPlanningError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalise_texts(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted({_require_text(field_name, value) for value in values}))
    return normalized


def _validate_sha256(field_name: str, value: str | None) -> None:
    if value is not None and not _SHA256_PATTERN.fullmatch(value):
        raise McpInstallationPlanningError(
            f"{field_name} must be a lowercase-or-uppercase sha256 digest with 64 hex characters"
        )


@dataclass(frozen=True, slots=True)
class McpPackageArtifactVerification:
    """Evidence emitted by a future artifact resolver/scanner, never registry metadata.

    ``artifact_digest`` and ``provenance_verified`` are intentionally separate:
    a digest makes an artifact reproducible, while provenance links it to an
    acceptable publisher or attestation. Both are required before automatic
    sandbox installation.
    """

    registry_type: str
    identifier: str
    version: str
    evidence_id: str
    artifact_digest: str | None
    provenance_verified: bool
    sbom_digest: str | None = None

    def __post_init__(self) -> None:
        _require_text("artifact.registry_type", self.registry_type)
        _require_text("artifact.identifier", self.identifier)
        _require_text("artifact.version", self.version)
        _require_text("artifact.evidence_id", self.evidence_id)
        if not isinstance(self.provenance_verified, bool):
            raise McpInstallationPlanningError("artifact.provenance_verified must be a boolean")
        _validate_sha256("artifact.artifact_digest", self.artifact_digest)
        _validate_sha256("artifact.sbom_digest", self.sbom_digest)


@dataclass(frozen=True, slots=True)
class McpRemoteEndpointVerification:
    """Evidence from a future endpoint verifier, without opening a connection here."""

    url: str
    transport: McpTransportType
    evidence_id: str
    tls_identity_verified: bool
    verified_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        url = _require_text("remote.url", self.url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise McpInstallationPlanningError("remote.url must be an absolute HTTP(S) URL")
        _require_text("remote.evidence_id", self.evidence_id)
        if not isinstance(self.transport, McpTransportType):
            raise McpInstallationPlanningError("remote.transport must be an MCP transport type")
        if not isinstance(self.tls_identity_verified, bool):
            raise McpInstallationPlanningError("remote.tls_identity_verified must be a boolean")
        if self.verified_at.tzinfo is None:
            raise McpInstallationPlanningError("remote.verified_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class McpInstallationPlan:
    """An immutable hand-off contract for a future isolated install worker.

    The plan deliberately records only *categories* of package/runtime
    arguments and only secret variable names. It never carries raw arbitrary
    launch arguments, environment values, OAuth tokens, or a runnable command.
    """

    plan_id: str
    capability_id: str
    candidate_id: str
    source_metadata_hash: str
    server_name: str
    server_version: str | None
    target: McpInstallTarget
    transport: McpTransportType
    target_reference: ArtifactReference
    policy_decision: PolicyDecision
    readiness: McpInstallReadiness
    review_reasons: tuple[str, ...]
    static_findings: tuple[McpStaticRiskFinding, ...]
    required_controls: tuple[str, ...]
    secret_variable_names: tuple[str, ...] = ()
    unconsumed_argument_kinds: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_text("plan.plan_id", self.plan_id)
        _require_text("plan.capability_id", self.capability_id)
        _require_text("plan.candidate_id", self.candidate_id)
        _require_text("plan.source_metadata_hash", self.source_metadata_hash)
        _validate_sha256("plan.source_metadata_hash", self.source_metadata_hash)
        _require_text("plan.server_name", self.server_name)
        if self.server_version is not None:
            _require_text("plan.server_version", self.server_version)
        if not isinstance(self.target, McpInstallTarget):
            raise McpInstallationPlanningError("plan.target must be an MCP installation target")
        if not isinstance(self.transport, McpTransportType):
            raise McpInstallationPlanningError("plan.transport must be an MCP transport type")
        if not isinstance(self.target_reference, ArtifactReference):
            raise McpInstallationPlanningError("plan.target_reference must be an artifact reference")
        if self.created_at.tzinfo is None:
            raise McpInstallationPlanningError("plan.created_at must be timezone-aware")
        object.__setattr__(self, "review_reasons", _normalise_texts("plan.review_reason", self.review_reasons))
        object.__setattr__(self, "required_controls", _normalise_texts("plan.required_control", self.required_controls))
        object.__setattr__(self, "secret_variable_names", _normalise_texts("plan.secret_variable_name", self.secret_variable_names))
        object.__setattr__(
            self,
            "unconsumed_argument_kinds",
            _normalise_texts("plan.unconsumed_argument_kind", self.unconsumed_argument_kinds),
        )
        if not self.required_controls:
            raise McpInstallationPlanningError("plan.required_controls must not be empty")
        if self.readiness is McpInstallReadiness.READY_FOR_SANDBOX and self.review_reasons:
            raise McpInstallationPlanningError("a ready plan may not retain review reasons")
        if self.readiness is McpInstallReadiness.PENDING_REVIEW and not self.review_reasons:
            raise McpInstallationPlanningError("a pending-review plan requires at least one reason")

    @property
    def ready_for_sandbox_execution(self) -> bool:
        """True only when all static, evidence, and policy gates have passed."""

        return self.readiness is McpInstallReadiness.READY_FOR_SANDBOX


class McpInstallationPlanBuilder:
    """Pure builder that turns selected metadata and evidence into a safe plan."""

    @classmethod
    def for_package(
        cls,
        *,
        manifest: McpServerManifest,
        package_index: int,
        verification: McpPackageArtifactVerification,
        capability_id: str,
        candidate_id: str,
        source_metadata_hash: str,
        policy_decision: PolicyDecision,
    ) -> McpInstallationPlan:
        package = cls._package_at(manifest, package_index)
        cls._require_permitted_policy(policy_decision)
        cls._ensure_package_matches(package, verification)

        review_reasons = cls._policy_review_reasons(policy_decision)
        if verification.artifact_digest is None:
            review_reasons.append("artifact-digest-missing")
        if not verification.provenance_verified:
            review_reasons.append("artifact-provenance-unverified")
        if package.package_arguments:
            review_reasons.append("package-arguments-require-approved-template")
        if package.runtime_arguments:
            review_reasons.append("runtime-arguments-require-approved-template")
        if not package.transport.is_core_transport:
            review_reasons.append("legacy-or-optional-transport")

        secret_names = tuple(
            variable.name for variable in package.environment_variables if variable.is_secret
        )
        argument_kinds: list[str] = []
        if package.package_arguments:
            argument_kinds.append("package")
        if package.runtime_arguments:
            argument_kinds.append("runtime")

        controls = [
            "artifact-digest-verification",
            "credential-free-mcp-probe",
            "immutable-tool-catalog-snapshot",
            "isolated-install-runtime",
            "sandboxed-process-execution",
        ]
        if secret_names:
            controls.append("secret-broker-before-activation")

        return cls._new_plan(
            manifest=manifest,
            capability_id=capability_id,
            candidate_id=candidate_id,
            source_metadata_hash=source_metadata_hash,
            target=McpInstallTarget.PACKAGE,
            transport=package.transport,
            target_reference=ArtifactReference(
                kind=f"mcp-package:{package.registry_type}",
                locator=package.identifier,
                version=verification.version,
                digest=verification.artifact_digest,
            ),
            policy_decision=policy_decision,
            review_reasons=review_reasons,
            static_findings=manifest.static_risk_findings(),
            required_controls=tuple(controls),
            secret_variable_names=secret_names,
            unconsumed_argument_kinds=tuple(argument_kinds),
        )

    @classmethod
    def for_remote(
        cls,
        *,
        manifest: McpServerManifest,
        remote_index: int,
        verification: McpRemoteEndpointVerification,
        capability_id: str,
        candidate_id: str,
        source_metadata_hash: str,
        policy_decision: PolicyDecision,
    ) -> McpInstallationPlan:
        remote = cls._remote_at(manifest, remote_index)
        cls._require_permitted_policy(policy_decision)
        if verification.url != remote.url:
            raise McpInstallationPlanningError("remote verification URL does not match the selected manifest remote")
        if verification.transport is not remote.transport:
            raise McpInstallationPlanningError(
                "remote verification transport does not match the selected manifest remote"
            )

        parsed = urlparse(remote.url)
        review_reasons = cls._policy_review_reasons(policy_decision)
        if parsed.scheme != "https":
            review_reasons.append("remote-endpoint-not-https")
        if parsed.username or parsed.password:
            review_reasons.append("remote-url-contains-userinfo")
        if remote.transport is not McpTransportType.STREAMABLE_HTTP:
            review_reasons.append("remote-transport-requires-compatibility-review")
        if not verification.tls_identity_verified:
            review_reasons.append("remote-tls-identity-unverified")
        if manifest.version is None:
            review_reasons.append("remote-server-version-unpinned")

        controls = [
            "credential-free-mcp-probe",
            "immutable-tool-catalog-snapshot",
            "origin-bound-authorization",
            "remote-origin-egress-allowlist",
            "server-side-request-forgery-protection",
        ]
        return cls._new_plan(
            manifest=manifest,
            capability_id=capability_id,
            candidate_id=candidate_id,
            source_metadata_hash=source_metadata_hash,
            target=McpInstallTarget.REMOTE,
            transport=remote.transport,
            target_reference=ArtifactReference(
                kind="mcp-remote-endpoint",
                locator=remote.url,
                version=manifest.version or "unversioned",
                digest=None,
            ),
            policy_decision=policy_decision,
            review_reasons=review_reasons,
            static_findings=manifest.static_risk_findings(),
            required_controls=tuple(controls),
        )

    @staticmethod
    def _package_at(manifest: McpServerManifest, package_index: int) -> McpPackageSpec:
        if not 0 <= package_index < len(manifest.packages):
            raise McpInstallationPlanningError("package_index does not select a declared package")
        return manifest.packages[package_index]

    @staticmethod
    def _remote_at(manifest: McpServerManifest, remote_index: int) -> McpRemoteSpec:
        if not 0 <= remote_index < len(manifest.remotes):
            raise McpInstallationPlanningError("remote_index does not select a declared remote")
        return manifest.remotes[remote_index]

    @staticmethod
    def _ensure_package_matches(
        package: McpPackageSpec,
        verification: McpPackageArtifactVerification,
    ) -> None:
        if verification.registry_type != package.registry_type:
            raise McpInstallationPlanningError("artifact registry type does not match the selected package")
        if verification.identifier != package.identifier:
            raise McpInstallationPlanningError("artifact identifier does not match the selected package")
        if package.version is not None and verification.version != package.version:
            raise McpInstallationPlanningError("artifact version does not match the selected package")

    @staticmethod
    def _require_permitted_policy(decision: PolicyDecision) -> None:
        if decision.kind is PolicyDecisionKind.DENY:
            raise McpInstallationPlanningError("a denied policy decision cannot produce an installation plan")
        if decision.kind is PolicyDecisionKind.REQUIRE_SANDBOX and not decision.obligations.get("sandbox"):
            raise McpInstallationPlanningError(
                "a sandbox policy decision must record its sandbox obligation"
            )

    @staticmethod
    def _policy_review_reasons(decision: PolicyDecision) -> list[str]:
        if decision.kind is PolicyDecisionKind.REQUIRE_APPROVAL:
            return ["policy-approval-required"]
        return []

    @staticmethod
    def _new_plan(
        *,
        manifest: McpServerManifest,
        capability_id: str,
        candidate_id: str,
        source_metadata_hash: str,
        target: McpInstallTarget,
        transport: McpTransportType,
        target_reference: ArtifactReference,
        policy_decision: PolicyDecision,
        review_reasons: list[str],
        static_findings: tuple[McpStaticRiskFinding, ...],
        required_controls: tuple[str, ...],
        secret_variable_names: tuple[str, ...] = (),
        unconsumed_argument_kinds: tuple[str, ...] = (),
    ) -> McpInstallationPlan:
        readiness = (
            McpInstallReadiness.PENDING_REVIEW
            if review_reasons
            else McpInstallReadiness.READY_FOR_SANDBOX
        )
        return McpInstallationPlan(
            plan_id=f"mcp-install:{uuid4()}",
            capability_id=capability_id,
            candidate_id=candidate_id,
            source_metadata_hash=source_metadata_hash,
            server_name=manifest.server_name,
            server_version=manifest.version,
            target=target,
            transport=transport,
            target_reference=target_reference,
            policy_decision=policy_decision,
            readiness=readiness,
            review_reasons=tuple(review_reasons),
            static_findings=static_findings,
            required_controls=required_controls,
            secret_variable_names=secret_variable_names,
            unconsumed_argument_kinds=unconsumed_argument_kinds,
        )
