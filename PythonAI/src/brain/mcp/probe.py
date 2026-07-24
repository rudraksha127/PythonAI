"""Validated, credential-free MCP probe output and immutable tool snapshots.

This module is deliberately transport-neutral. A future MCP client performs
``initialize`` and the list calls; it must normalize that wire output into the
contracts below. ForgeAI accepts it only when it is tied to a sandbox-ready
installation plan, contains no credential use, and has safe bounded JSON
schemas. No code here opens a socket or invokes a tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping
from uuid import uuid4

from ..domain.models import ArtifactReference, freeze_mapping, utc_now
from .installation import McpInstallationPlan
from .server_manifest import McpTransportType


_PROTOCOL_VERSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SNAPSHOT_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_SCHEMA_NODES = 2_000
_MAX_SCHEMA_DEPTH = 32
_MAX_SCHEMA_BYTES = 256_000
_MAX_TOOLS = 256
_MAX_RESOURCES = 512
_MAX_PROMPTS = 128


class McpProbeValidationError(ValueError):
    """Raised when a probe result cannot safely become an exposed catalog."""


def _text(field_name: str, value: str, *, max_length: int = 10_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpProbeValidationError(f"{field_name} must be a non-empty string")
    result = value.strip()
    if len(result) > max_length:
        raise McpProbeValidationError(f"{field_name} exceeds the maximum length")
    if any(not character.isprintable() for character in result):
        raise McpProbeValidationError(f"{field_name} may not contain control characters")
    return result


def _identifier(field_name: str, value: str) -> str:
    result = _text(field_name, value, max_length=256)
    if any(character.isspace() for character in result):
        raise McpProbeValidationError(f"{field_name} may not contain whitespace")
    return result


def _json_ready(value: Any, field_name: str, *, depth: int = 0, nodes: list[int] | None = None) -> Any:
    """Validate JSON-like metadata without resolving external schema references."""

    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > _MAX_SCHEMA_NODES:
        raise McpProbeValidationError(f"{field_name} exceeds the maximum JSON node count")
    if depth > _MAX_SCHEMA_DEPTH:
        raise McpProbeValidationError(f"{field_name} exceeds the maximum JSON depth")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise McpProbeValidationError(f"{field_name} may not contain non-finite floats")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise McpProbeValidationError(f"{field_name} JSON object keys must be strings")
            if key in {"$ref", "$dynamicRef"}:
                if not isinstance(item, str) or not item.startswith("#"):
                    raise McpProbeValidationError(
                        f"{field_name}.{key} must be an internal JSON-pointer reference"
                    )
            normalized[key] = _json_ready(item, field_name, depth=depth + 1, nodes=nodes)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_ready(item, field_name, depth=depth + 1, nodes=nodes) for item in value]
    raise McpProbeValidationError(f"{field_name} must contain only JSON values")


def _json_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProbeValidationError(f"{field_name} must be a JSON object")
    normalized = _json_ready(value, field_name)
    try:
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:  # Defensive: _json_ready should already reject this.
        raise McpProbeValidationError(f"{field_name} could not be encoded as JSON") from error
    if len(encoded) > _MAX_SCHEMA_BYTES:
        raise McpProbeValidationError(f"{field_name} exceeds the maximum serialized JSON size")
    return freeze_mapping(normalized)


def _unique_identifiers(field_name: str, values: tuple[Any, ...], attribute: str = "name") -> None:
    identifiers = [getattr(value, attribute) for value in values]
    if len(set(identifiers)) != len(identifiers):
        raise McpProbeValidationError(f"{field_name} must not contain duplicate {attribute} values")


@dataclass(frozen=True, slots=True)
class McpToolDescriptor:
    """A normalized tool declaration captured from ``tools/list``."""

    name: str
    description: str | None
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None = None
    annotations: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier("tool.name", self.name))
        if self.description is not None:
            object.__setattr__(self, "description", _text("tool.description", self.description))
        object.__setattr__(self, "input_schema", _json_mapping(self.input_schema, "tool.input_schema"))
        if self.output_schema is not None:
            object.__setattr__(
                self,
                "output_schema",
                _json_mapping(self.output_schema, "tool.output_schema"),
            )
        object.__setattr__(self, "annotations", _json_mapping(self.annotations, "tool.annotations"))


@dataclass(frozen=True, slots=True)
class McpResourceDescriptor:
    """Metadata-only resource declaration captured from ``resources/list``."""

    uri: str
    name: str
    description: str | None = None
    mime_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "uri", _text("resource.uri", self.uri, max_length=4_096))
        object.__setattr__(self, "name", _text("resource.name", self.name))
        if self.description is not None:
            object.__setattr__(self, "description", _text("resource.description", self.description))
        if self.mime_type is not None:
            object.__setattr__(self, "mime_type", _text("resource.mime_type", self.mime_type, max_length=256))


@dataclass(frozen=True, slots=True)
class McpPromptDescriptor:
    """Metadata-only prompt declaration captured from ``prompts/list``."""

    name: str
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier("prompt.name", self.name))
        if self.description is not None:
            object.__setattr__(self, "description", _text("prompt.description", self.description))


@dataclass(frozen=True, slots=True)
class McpProbeExecutionEvidence:
    """Attestation supplied by the isolated worker that performed a probe."""

    probe_id: str
    isolated_runtime_id: str
    credential_free: bool
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_id", _text("probe.probe_id", self.probe_id, max_length=256))
        object.__setattr__(
            self,
            "isolated_runtime_id",
            _text("probe.isolated_runtime_id", self.isolated_runtime_id, max_length=256),
        )
        if not isinstance(self.credential_free, bool):
            raise McpProbeValidationError("probe.credential_free must be a boolean")
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise McpProbeValidationError("probe timestamps must be timezone-aware")
        if self.completed_at < self.started_at:
            raise McpProbeValidationError("probe completion may not precede probe start")


@dataclass(frozen=True, slots=True)
class McpProbeTranscript:
    """Typed result of initialize and all metadata-list probe calls."""

    server_name: str
    protocol_version: str
    transport: McpTransportType
    execution: McpProbeExecutionEvidence
    tools: tuple[McpToolDescriptor, ...]
    resources: tuple[McpResourceDescriptor, ...]
    prompts: tuple[McpPromptDescriptor, ...]
    tools_listed: bool
    resources_listed: bool
    prompts_listed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "server_name", _text("probe.server_name", self.server_name, max_length=512))
        if not isinstance(self.protocol_version, str) or not _PROTOCOL_VERSION_PATTERN.fullmatch(
            self.protocol_version
        ):
            raise McpProbeValidationError("probe.protocol_version must use YYYY-MM-DD format")
        if not isinstance(self.transport, McpTransportType):
            raise McpProbeValidationError("probe.transport must be an MCP transport type")
        if not isinstance(self.execution, McpProbeExecutionEvidence):
            raise McpProbeValidationError("probe.execution must be probe execution evidence")
        for listed_name in ("tools_listed", "resources_listed", "prompts_listed"):
            if not isinstance(getattr(self, listed_name), bool):
                raise McpProbeValidationError(f"probe.{listed_name} must be a boolean")
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "prompts", tuple(self.prompts))
        if any(not isinstance(tool, McpToolDescriptor) for tool in self.tools):
            raise McpProbeValidationError("probe.tools must contain MCP tool descriptors")
        if any(not isinstance(resource, McpResourceDescriptor) for resource in self.resources):
            raise McpProbeValidationError("probe.resources must contain MCP resource descriptors")
        if any(not isinstance(prompt, McpPromptDescriptor) for prompt in self.prompts):
            raise McpProbeValidationError("probe.prompts must contain MCP prompt descriptors")
        if len(self.tools) > _MAX_TOOLS:
            raise McpProbeValidationError("probe.tools exceeds the configured maximum")
        if len(self.resources) > _MAX_RESOURCES:
            raise McpProbeValidationError("probe.resources exceeds the configured maximum")
        if len(self.prompts) > _MAX_PROMPTS:
            raise McpProbeValidationError("probe.prompts exceeds the configured maximum")
        _unique_identifiers("probe.tools", self.tools)
        _unique_identifiers("probe.resources", self.resources, attribute="uri")
        _unique_identifiers("probe.prompts", self.prompts)
        if not self.tools_listed and self.tools:
            raise McpProbeValidationError("probe.tools may not be supplied before tools/list succeeds")
        if not self.resources_listed and self.resources:
            raise McpProbeValidationError("probe.resources may not be supplied before resources/list succeeds")
        if not self.prompts_listed and self.prompts:
            raise McpProbeValidationError("probe.prompts may not be supplied before prompts/list succeeds")


@dataclass(frozen=True, slots=True)
class McpToolCatalogSnapshot:
    """Immutable, hash-addressed catalog resulting from a successful probe."""

    snapshot_id: str
    snapshot_hash: str
    plan_id: str
    capability_id: str
    server_name: str
    protocol_version: str
    transport: McpTransportType
    target_reference: ArtifactReference
    probe_id: str
    tools: tuple[McpToolDescriptor, ...]
    resources: tuple[McpResourceDescriptor, ...]
    prompts: tuple[McpPromptDescriptor, ...]
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _text("snapshot.snapshot_id", self.snapshot_id, max_length=256))
        if not _SNAPSHOT_DIGEST_PATTERN.fullmatch(self.snapshot_hash):
            raise McpProbeValidationError("snapshot.snapshot_hash must be a sha256 digest")
        object.__setattr__(self, "plan_id", _text("snapshot.plan_id", self.plan_id, max_length=256))
        object.__setattr__(self, "capability_id", _text("snapshot.capability_id", self.capability_id, max_length=512))
        object.__setattr__(self, "server_name", _text("snapshot.server_name", self.server_name, max_length=512))
        if not _PROTOCOL_VERSION_PATTERN.fullmatch(self.protocol_version):
            raise McpProbeValidationError("snapshot.protocol_version must use YYYY-MM-DD format")
        if not isinstance(self.transport, McpTransportType):
            raise McpProbeValidationError("snapshot.transport must be an MCP transport type")
        if not isinstance(self.target_reference, ArtifactReference):
            raise McpProbeValidationError("snapshot.target_reference must be an artifact reference")
        object.__setattr__(self, "probe_id", _text("snapshot.probe_id", self.probe_id, max_length=256))
        if self.created_at.tzinfo is None:
            raise McpProbeValidationError("snapshot.created_at must be timezone-aware")
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "prompts", tuple(self.prompts))


class McpProbeSnapshotBuilder:
    """Pure acceptance gate between an isolated MCP probe and ForgeAI's catalog."""

    @classmethod
    def from_transcript(
        cls,
        *,
        plan: McpInstallationPlan,
        transcript: McpProbeTranscript,
    ) -> McpToolCatalogSnapshot:
        if not plan.ready_for_sandbox_execution:
            raise McpProbeValidationError("only sandbox-ready installation plans may be probed")
        if transcript.server_name != plan.server_name:
            raise McpProbeValidationError("probe server identity does not match the installation plan")
        if transcript.transport is not plan.transport:
            raise McpProbeValidationError("probe transport does not match the installation plan")
        if not transcript.execution.credential_free:
            raise McpProbeValidationError("credential-bearing probes may not expose a tool catalog")
        if not (transcript.tools_listed and transcript.resources_listed and transcript.prompts_listed):
            raise McpProbeValidationError(
                "probe must complete tools/list, resources/list, and prompts/list before registration"
            )
        snapshot_hash = cls._snapshot_hash(plan, transcript)
        return McpToolCatalogSnapshot(
            snapshot_id=f"mcp-tools:{uuid4()}",
            snapshot_hash=snapshot_hash,
            plan_id=plan.plan_id,
            capability_id=plan.capability_id,
            server_name=transcript.server_name,
            protocol_version=transcript.protocol_version,
            transport=transcript.transport,
            target_reference=plan.target_reference,
            probe_id=transcript.execution.probe_id,
            tools=transcript.tools,
            resources=transcript.resources,
            prompts=transcript.prompts,
        )

    @staticmethod
    def _snapshot_hash(plan: McpInstallationPlan, transcript: McpProbeTranscript) -> str:
        payload = {
            "plan_id": plan.plan_id,
            "capability_id": plan.capability_id,
            "server_name": transcript.server_name,
            "protocol_version": transcript.protocol_version,
            "transport": transcript.transport.value,
            "target": {
                "kind": plan.target_reference.kind,
                "locator": plan.target_reference.locator,
                "version": plan.target_reference.version,
                "digest": plan.target_reference.digest,
            },
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                    "annotations": tool.annotations,
                }
                for tool in transcript.tools
            ],
            "resources": [
                {
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description,
                    "mime_type": resource.mime_type,
                }
                for resource in transcript.resources
            ],
            "prompts": [
                {"name": prompt.name, "description": prompt.description}
                for prompt in transcript.prompts
            ],
        }
        try:
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=dict).encode("utf-8")
        except (TypeError, ValueError) as error:  # Defensive: descriptors already validate JSON metadata.
            raise McpProbeValidationError("probe catalog cannot be canonically encoded") from error
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
