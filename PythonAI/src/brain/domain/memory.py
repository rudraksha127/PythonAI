"""Hybrid-memory contracts with tenant boundaries, provenance, and retention."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping
from uuid import uuid4

from .models import freeze_mapping, utc_now


class MemoryValidationError(ValueError):
    """Raised when a memory write, record, or retrieval request is invalid."""


class MemoryScope(str, Enum):
    """Replaceable memory projections required by the autonomous-brain design."""

    CONVERSATION = "conversation"
    TASK = "task"
    PROJECT = "project"
    KNOWLEDGE = "knowledge"
    CODE = "code"
    EXECUTION = "execution"
    LONG_TERM = "long-term"
    SEMANTIC = "semantic"
    GRAPH = "graph"


class MemorySensitivity(str, Enum):
    """Secret values belong in a secret broker, not in an AI memory store."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


MEMORY_SENSITIVITY_ORDER: Mapping[MemorySensitivity, int] = {
    MemorySensitivity.PUBLIC: 0,
    MemorySensitivity.INTERNAL: 1,
    MemorySensitivity.SENSITIVE: 2,
}


def _text(field_name: str, value: str, *, maximum: int = 100_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryValidationError(f"{field_name} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum:
        raise MemoryValidationError(f"{field_name} exceeds the maximum length")
    return result


def _content(field_name: str, value: str, *, maximum: int = 100_000) -> str:
    """Validate stored bytes without rewriting code or conversation whitespace."""

    if not isinstance(value, str) or not value.strip():
        raise MemoryValidationError(f"{field_name} must be a non-empty string")
    if len(value) > maximum:
        raise MemoryValidationError(f"{field_name} exceeds the maximum length")
    return value


def _tags(
    values: frozenset[str] | set[str] | tuple[str, ...] | list[str],
) -> frozenset[str]:
    if isinstance(values, str) or not isinstance(values, (frozenset, set, tuple, list)):
        raise MemoryValidationError("memory tags must be a collection of strings")
    normalized = frozenset(_text("memory.tag", value, maximum=256) for value in values)
    if len(normalized) != len(values):
        raise MemoryValidationError("memory tags must be unique")
    return normalized


def _metadata(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept bounded JSON metadata while rejecting obvious secret-bearing fields.

    Content may be submitted only after the caller's DLP/redaction extension has
    classified it. This guard prevents a connector from smuggling a credential
    into a supposedly descriptive metadata field.
    """

    if not isinstance(value, Mapping):
        raise MemoryValidationError("memory.metadata must be an object")
    forbidden_fragments = (
        "secret",
        "password",
        "credential",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "private_key",
    )
    for key in value:
        if not isinstance(key, str) or not key.strip():
            raise MemoryValidationError("memory.metadata keys must be non-empty strings")
        if any(fragment in key.casefold() for fragment in forbidden_fragments):
            raise MemoryValidationError("memory.metadata may not contain secret-bearing fields")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise MemoryValidationError("memory.metadata must be bounded JSON-compatible data") from error
    if len(encoded.encode("utf-8")) > 65_536:
        raise MemoryValidationError("memory.metadata exceeds the maximum encoded size")
    return freeze_mapping(value)


@dataclass(frozen=True, slots=True)
class MemoryWriteRequest:
    """A provenance-rich write request with explicit secret classification guards.

    Explicitly secret-classified data is rejected. Callers must run any required
    DLP/redaction plugin before passing untrusted source content to this contract.
    """

    tenant_id: str
    workspace_id: str
    scope: MemoryScope
    subject_id: str
    content: str
    provenance_id: str
    source_kind: str
    tags: frozenset[str] = field(default_factory=frozenset)
    sensitivity: MemorySensitivity = MemorySensitivity.INTERNAL
    expires_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text("memory.tenant_id", self.tenant_id, maximum=256))
        object.__setattr__(self, "workspace_id", _text("memory.workspace_id", self.workspace_id, maximum=256))
        if not isinstance(self.scope, MemoryScope):
            raise MemoryValidationError("memory.scope must be a memory scope")
        object.__setattr__(self, "subject_id", _text("memory.subject_id", self.subject_id, maximum=512))
        object.__setattr__(self, "content", _content("memory.content", self.content, maximum=250_000))
        object.__setattr__(self, "provenance_id", _text("memory.provenance_id", self.provenance_id, maximum=512))
        object.__setattr__(self, "source_kind", _text("memory.source_kind", self.source_kind, maximum=256))
        object.__setattr__(self, "tags", _tags(self.tags))
        if not isinstance(self.sensitivity, MemorySensitivity):
            raise MemoryValidationError("memory.sensitivity must be a memory sensitivity")
        if self.sensitivity is MemorySensitivity.SECRET:
            raise MemoryValidationError("secret values must be stored in the secret broker, not memory")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise MemoryValidationError("memory.expires_at must be timezone-aware")
            if self.expires_at <= utc_now():
                raise MemoryValidationError("memory.expires_at must be in the future")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def content_hash(self) -> str:
        """Deduplication hash; stores scope it by tenant/workspace/scope/subject."""

        return f"sha256:{hashlib.sha256(self.content.encode('utf-8')).hexdigest()}"

    @property
    def deduplication_key(self) -> str:
        """Exact observation identity that preserves provenance and retention semantics."""

        payload = {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "scope": self.scope.value,
            "subject_id": self.subject_id,
            "content_hash": self.content_hash,
            "provenance_id": self.provenance_id,
            "source_kind": self.source_kind,
            "tags": sorted(self.tags),
            "sensitivity": self.sensitivity.value,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
        return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """An immutable memory entry kept separate from secrets and raw execution credentials."""

    memory_id: str
    tenant_id: str
    workspace_id: str
    scope: MemoryScope
    subject_id: str
    content: str
    content_hash: str
    provenance_id: str
    source_kind: str
    tags: frozenset[str]
    sensitivity: MemorySensitivity
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    untrusted_content: bool = True

    def __post_init__(self) -> None:
        for field_name, maximum in (
            ("memory_id", 512),
            ("tenant_id", 256),
            ("workspace_id", 256),
            ("subject_id", 512),
            ("content_hash", 256),
            ("content_hash", 256),
            ("provenance_id", 512),
            ("source_kind", 256),
        ):
            object.__setattr__(self, field_name, _text(f"record.{field_name}", getattr(self, field_name), maximum=maximum))
        object.__setattr__(self, "content", _content("record.content", self.content, maximum=250_000))
        if not isinstance(self.scope, MemoryScope):
            raise MemoryValidationError("record.scope must be a memory scope")
        object.__setattr__(self, "tags", _tags(self.tags))
        if not isinstance(self.sensitivity, MemorySensitivity) or self.sensitivity is MemorySensitivity.SECRET:
            raise MemoryValidationError("record.sensitivity may not be secret")
        expected_hash = f"sha256:{hashlib.sha256(self.content.encode('utf-8')).hexdigest()}"
        if self.content_hash != expected_hash:
            raise MemoryValidationError("record.content_hash must match immutable content")
        if self.created_at.tzinfo is None:
            raise MemoryValidationError("record.created_at must be timezone-aware")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise MemoryValidationError("record.expires_at must be timezone-aware")
            if self.expires_at <= self.created_at:
                raise MemoryValidationError("record.expires_at must follow record.created_at")
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        if self.untrusted_content is not True:
            raise MemoryValidationError("memory content must remain marked untrusted")

    @property
    def is_expired(self) -> bool:
        """Expiration is evaluated at read time so cleanup remains a replaceable adapter concern."""

        return self.expires_at is not None and self.expires_at <= utc_now()


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    """Tenant/workspace-bound memory search request."""

    tenant_id: str
    workspace_id: str
    query: str
    scopes: frozenset[MemoryScope] = field(default_factory=lambda: frozenset(MemoryScope))
    subject_id: str | None = None
    maximum_results: int = 10
    maximum_sensitivity: MemorySensitivity = MemorySensitivity.INTERNAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text("query.tenant_id", self.tenant_id, maximum=256))
        object.__setattr__(self, "workspace_id", _text("query.workspace_id", self.workspace_id, maximum=256))
        object.__setattr__(self, "query", _text("query.query", self.query, maximum=10_000))
        object.__setattr__(self, "scopes", frozenset(self.scopes))
        if not self.scopes or any(not isinstance(scope, MemoryScope) for scope in self.scopes):
            raise MemoryValidationError("query.scopes must contain memory scopes")
        if self.subject_id is not None:
            object.__setattr__(self, "subject_id", _text("query.subject_id", self.subject_id, maximum=512))
        if not isinstance(self.maximum_results, int) or isinstance(self.maximum_results, bool):
            raise MemoryValidationError("query.maximum_results must be an integer")
        if not 1 <= self.maximum_results <= 100:
            raise MemoryValidationError("query.maximum_results must be between 1 and 100")
        if not isinstance(self.maximum_sensitivity, MemorySensitivity):
            raise MemoryValidationError("query.maximum_sensitivity must be a memory sensitivity")
        if self.maximum_sensitivity is MemorySensitivity.SECRET:
            raise MemoryValidationError("secret values cannot be retrieved from memory")


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """A cited, untrusted memory record returned by a pluggable retrieval projection."""

    record: MemoryRecord
    score: float

    def __post_init__(self) -> None:
        if not isinstance(self.record, MemoryRecord):
            raise MemoryValidationError("memory result must reference a memory record")
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not math.isfinite(self.score)
            or self.score < 0
        ):
            raise MemoryValidationError("memory result score must be non-negative")
        object.__setattr__(self, "score", float(self.score))


def new_memory_id() -> str:
    """Generate an opaque memory identifier distinct from content hashes and source IDs."""

    return f"memory:{uuid4()}"
