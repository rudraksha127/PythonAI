"""Stable, framework-free contracts for ForgeAI's capability control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Any, Mapping


def utc_now() -> datetime:
    """Return a timezone-aware timestamp suitable for persisted contracts."""

    return datetime.now(timezone.utc)


def _require_text(field_name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _normalise_strings(values: frozenset[str] | set[str] | tuple[str, ...] | list[str]) -> frozenset[str]:
    normalised = frozenset(value.strip() for value in values if value and value.strip())
    if len(normalised) != len(values):
        raise ValueError("string collections may not contain blank values")
    return normalised


def _freeze_value(value: Any) -> Any:
    """Recursively freeze JSON-like values held by immutable domain objects."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_value(item) for item in value)
    return value


def freeze_mapping(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Create a recursively immutable mapping from an untrusted metadata value."""

    return _freeze_value(value or {})


class RiskLevel(str, Enum):
    """The potential impact of invoking or installing a capability."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_ORDER: Mapping[RiskLevel, int] = MappingProxyType(
    {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }
)


class TrustTier(IntEnum):
    """Evidence quality for a discovery candidate, not an execution permission."""

    UNTRUSTED = 0
    COMMUNITY = 1
    VERIFIED = 2
    OFFICIAL = 3


class PluginRuntime(str, Enum):
    """Supported execution forms for a plugin implementation."""

    PYTHON_WORKER = "python-worker"
    NODE_WORKER = "node-worker"
    CONTAINER = "container"
    WASM = "wasm"
    REMOTE = "remote"


class CapabilityStatus(str, Enum):
    """Durable lifecycle state of a resolved capability release."""

    CANDIDATE = "candidate"
    VALIDATED = "validated"
    APPROVED = "approved"
    INSTALLING = "installing"
    INSTALLED = "installed"
    PROBING = "probing"
    ACTIVE = "active"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class PolicyAction(str, Enum):
    """Actions independently evaluated by the policy decision point."""

    DISCOVER = "discover"
    INSTALL = "install"
    ACTIVATE = "activate"
    EXECUTE = "execute"
    READ_SECRET = "read-secret"
    WRITE_MEMORY = "write-memory"
    READ_MEMORY = "read-memory"


class PolicyDecisionKind(str, Enum):
    """Fail-closed outcomes understood by policy enforcement points."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require-approval"
    REQUIRE_SANDBOX = "require-sandbox"


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """An immutable pointer to a plugin artifact or remote endpoint."""

    kind: str
    locator: str
    version: str
    digest: str | None = None

    def __post_init__(self) -> None:
        _require_text("artifact.kind", self.kind)
        _require_text("artifact.locator", self.locator)
        _require_text("artifact.version", self.version)
        if self.digest is not None:
            _require_text("artifact.digest", self.digest)


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """Provider-independent contract offered to the planner and runtime."""

    capability_id: str
    version: str
    name: str
    description: str
    kind: str
    risk_level: RiskLevel
    tags: frozenset[str] = field(default_factory=frozenset)
    required_permissions: frozenset[str] = field(default_factory=frozenset)
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("capability_id", self.capability_id)
        _require_text("capability.version", self.version)
        _require_text("capability.name", self.name)
        _require_text("capability.description", self.description)
        _require_text("capability.kind", self.kind)
        object.__setattr__(self, "tags", _normalise_strings(self.tags))
        object.__setattr__(self, "required_permissions", _normalise_strings(self.required_permissions))
        object.__setattr__(self, "input_schema", freeze_mapping(self.input_schema))
        object.__setattr__(self, "output_schema", freeze_mapping(self.output_schema))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    """A provenance-preserving discovery observation.

    A candidate is intentionally not an executable installation instruction.
    It becomes executable only after policy, artifact, and dynamic probe stages.
    """

    candidate_id: str
    capability_id: str
    source_name: str
    source_url: str
    trust_tier: TrustTier
    artifact: ArtifactReference
    raw_metadata_hash: str
    observed_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("candidate_id", self.candidate_id)
        _require_text("candidate.capability_id", self.capability_id)
        _require_text("candidate.source_name", self.source_name)
        _require_text("candidate.source_url", self.source_url)
        _require_text("candidate.raw_metadata_hash", self.raw_metadata_hash)
        if self.observed_at.tzinfo is None:
            raise ValueError("candidate.observed_at must be timezone-aware")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Validated plugin declaration independent of its implementation language."""

    plugin_id: str
    version: str
    publisher: str
    kind: str
    runtime: PluginRuntime
    entrypoint: str
    provided_capability_ids: tuple[str, ...]
    requested_permissions: frozenset[str] = field(default_factory=frozenset)
    api_version: str = "forgeai.dev/plugin/v1"
    compatibility: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("plugin_id", self.plugin_id)
        _require_text("plugin.version", self.version)
        _require_text("plugin.publisher", self.publisher)
        _require_text("plugin.kind", self.kind)
        _require_text("plugin.entrypoint", self.entrypoint)
        _require_text("plugin.api_version", self.api_version)
        if not self.provided_capability_ids:
            raise ValueError("plugin.provided_capability_ids must not be empty")
        if len(set(self.provided_capability_ids)) != len(self.provided_capability_ids):
            raise ValueError("plugin.provided_capability_ids must be unique")
        for capability_id in self.provided_capability_ids:
            _require_text("plugin.provided_capability_id", capability_id)
        object.__setattr__(self, "requested_permissions", _normalise_strings(self.requested_permissions))
        object.__setattr__(self, "compatibility", freeze_mapping(self.compatibility))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    """The catalog's current immutable view of one capability release."""

    descriptor: CapabilityDescriptor
    candidate: CapabilityCandidate
    manifest: PluginManifest
    status: CapabilityStatus = CapabilityStatus.CANDIDATE
    revision: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    last_transition_reason: str | None = None

    def __post_init__(self) -> None:
        if self.descriptor.capability_id != self.candidate.capability_id:
            raise ValueError("record descriptor and candidate capability IDs must match")
        if self.descriptor.capability_id not in self.manifest.provided_capability_ids:
            raise ValueError("record capability must be declared by its plugin manifest")
        if self.revision < 0:
            raise ValueError("record.revision must be non-negative")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("record timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("record.updated_at may not precede record.created_at")

    @property
    def capability_id(self) -> str:
        return self.descriptor.capability_id


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """A planner request expressed without a provider or package dependency."""

    requirement_id: str
    kind: str | None = None
    capability_ids: frozenset[str] = field(default_factory=frozenset)
    required_tags: frozenset[str] = field(default_factory=frozenset)
    allowed_risk_levels: frozenset[RiskLevel] = field(
        default_factory=lambda: frozenset(RiskLevel)
    )
    minimum_trust_tier: TrustTier = TrustTier.COMMUNITY

    def __post_init__(self) -> None:
        _require_text("requirement_id", self.requirement_id)
        if self.kind is not None:
            _require_text("requirement.kind", self.kind)
        object.__setattr__(self, "capability_ids", _normalise_strings(self.capability_ids))
        object.__setattr__(self, "required_tags", _normalise_strings(self.required_tags))
        if not self.allowed_risk_levels:
            raise ValueError("requirement.allowed_risk_levels must not be empty")


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    """All policy-relevant facts required for a deterministic decision."""

    action: PolicyAction
    principal_id: str
    tenant_id: str
    workspace_id: str
    capability_id: str
    risk_level: RiskLevel
    trust_tier: TrustTier
    requested_permissions: frozenset[str] = field(default_factory=frozenset)
    automated: bool = False
    sandboxed: bool = False
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("policy.principal_id", self.principal_id)
        _require_text("policy.tenant_id", self.tenant_id)
        _require_text("policy.workspace_id", self.workspace_id)
        _require_text("policy.capability_id", self.capability_id)
        object.__setattr__(self, "requested_permissions", _normalise_strings(self.requested_permissions))
        object.__setattr__(self, "context", freeze_mapping(self.context))


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Explainable output from the policy decision point."""

    kind: PolicyDecisionKind
    reason_code: str
    policy_version: str
    rule_id: str | None = None
    obligations: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("policy.reason_code", self.reason_code)
        _require_text("policy.policy_version", self.policy_version)
        object.__setattr__(self, "obligations", freeze_mapping(self.obligations))

    @property
    def permits_progress(self) -> bool:
        """Whether an enforcement point may continue without human approval."""

        return self.kind in {PolicyDecisionKind.ALLOW, PolicyDecisionKind.REQUIRE_SANDBOX}
