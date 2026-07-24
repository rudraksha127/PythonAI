"""Versioned, provenance-preserving knowledge contracts for ForgeAI RAG.

Knowledge is stored as untrusted content plus explicit source references. It is
never treated as an instruction stream, and every retrieval result carries a
stable citation back to content and source version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from typing import Any, Mapping

from .models import TrustTier, freeze_mapping, utc_now


class KnowledgeValidationError(ValueError):
    """Raised when knowledge records violate tenant, provenance, or citation invariants."""


def _text(field_name: str, value: str, *, maximum: int = 100_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeValidationError(f"{field_name} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum:
        raise KnowledgeValidationError(f"{field_name} exceeds the maximum length")
    return result


@dataclass(frozen=True, slots=True)
class KnowledgeSourceReference:
    """One versioned source asserting provenance for a content-addressed document."""

    source_id: str
    source_uri: str
    source_version: str
    trust_tier: TrustTier
    retrieved_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text("source.source_id", self.source_id, maximum=512))
        object.__setattr__(self, "source_uri", _text("source.source_uri", self.source_uri, maximum=4_096))
        object.__setattr__(
            self,
            "source_version",
            _text("source.source_version", self.source_version, maximum=512),
        )
        if not isinstance(self.trust_tier, TrustTier):
            raise KnowledgeValidationError("source.trust_tier must be a trust tier")
        if self.retrieved_at.tzinfo is None:
            raise KnowledgeValidationError("source.retrieved_at must be timezone-aware")

    @property
    def identity(self) -> tuple[str, str, str]:
        """Stable source-version identity used when deduplicating references."""

        return (self.source_id, self.source_uri, self.source_version)


@dataclass(frozen=True, slots=True)
class KnowledgeIngestRequest:
    """Raw content submitted by a connector after it has fetched a source."""

    tenant_id: str
    workspace_id: str
    title: str
    content: str
    content_type: str
    source: KnowledgeSourceReference
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text("ingest.tenant_id", self.tenant_id, maximum=256))
        object.__setattr__(self, "workspace_id", _text("ingest.workspace_id", self.workspace_id, maximum=256))
        object.__setattr__(self, "title", _text("ingest.title", self.title, maximum=1_024))
        object.__setattr__(self, "content", _text("ingest.content", self.content, maximum=5_000_000))
        object.__setattr__(self, "content_type", _text("ingest.content_type", self.content_type, maximum=256))
        if not isinstance(self.source, KnowledgeSourceReference):
            raise KnowledgeValidationError("ingest.source must be a source reference")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    @property
    def content_hash(self) -> str:
        """Content-addressable deduplication key, scoped by tenant/workspace in storage."""

        return f"sha256:{hashlib.sha256(self.content.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Immutable deduplicated content with one or more explicit provenance sources."""

    document_id: str
    tenant_id: str
    workspace_id: str
    content_hash: str
    title: str
    content: str
    content_type: str
    sources: tuple[KnowledgeSourceReference, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=utc_now)
    untrusted_content: bool = True

    def __post_init__(self) -> None:
        for field_name, maximum in (
            ("document_id", 512),
            ("tenant_id", 256),
            ("workspace_id", 256),
            ("content_hash", 256),
            ("title", 1_024),
            ("content", 5_000_000),
            ("content_type", 256),
        ):
            object.__setattr__(self, field_name, _text(f"document.{field_name}", getattr(self, field_name), maximum=maximum))
        expected_hash = f"sha256:{hashlib.sha256(self.content.encode('utf-8')).hexdigest()}"
        if self.content_hash != expected_hash:
            raise KnowledgeValidationError("document.content_hash must match the immutable document content")
        object.__setattr__(self, "sources", tuple(self.sources))
        if not self.sources or any(not isinstance(source, KnowledgeSourceReference) for source in self.sources):
            raise KnowledgeValidationError("document.sources must contain at least one source reference")
        identities = [source.identity for source in self.sources]
        if len(set(identities)) != len(identities):
            raise KnowledgeValidationError("document.sources must not duplicate a source version")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if self.ingested_at.tzinfo is None:
            raise KnowledgeValidationError("document.ingested_at must be timezone-aware")
        if self.untrusted_content is not True:
            raise KnowledgeValidationError("retrieved knowledge content must remain marked untrusted")

    @property
    def effective_trust_tier(self) -> TrustTier:
        """Highest provenance tier among exact content-identical source references."""

        return max(source.trust_tier for source in self.sources)


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A bounded retrievable slice of a knowledge document."""

    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    text_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _text("chunk.chunk_id", self.chunk_id, maximum=512))
        object.__setattr__(self, "document_id", _text("chunk.document_id", self.document_id, maximum=512))
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 0:
            raise KnowledgeValidationError("chunk.ordinal must be a non-negative integer")
        object.__setattr__(self, "text", _text("chunk.text", self.text, maximum=100_000))
        object.__setattr__(self, "text_hash", _text("chunk.text_hash", self.text_hash, maximum=256))
        expected_hash = f"sha256:{hashlib.sha256(self.text.encode('utf-8')).hexdigest()}"
        if self.text_hash != expected_hash:
            raise KnowledgeValidationError("chunk.text_hash must match immutable chunk text")


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    """Tenant-scoped retrieval request that never crosses workspace boundaries."""

    tenant_id: str
    workspace_id: str
    query: str
    maximum_results: int = 10
    minimum_trust_tier: TrustTier = TrustTier.COMMUNITY

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text("query.tenant_id", self.tenant_id, maximum=256))
        object.__setattr__(self, "workspace_id", _text("query.workspace_id", self.workspace_id, maximum=256))
        object.__setattr__(self, "query", _text("query.query", self.query, maximum=10_000))
        if not isinstance(self.maximum_results, int) or isinstance(self.maximum_results, bool):
            raise KnowledgeValidationError("query.maximum_results must be an integer")
        if not 1 <= self.maximum_results <= 100:
            raise KnowledgeValidationError("query.maximum_results must be between 1 and 100")
        if not isinstance(self.minimum_trust_tier, TrustTier):
            raise KnowledgeValidationError("query.minimum_trust_tier must be a trust tier")


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    """A bounded untrusted chunk plus a verifiable source-version citation."""

    document_id: str
    chunk_id: str
    score: float
    text: str
    source: KnowledgeSourceReference
    content_hash: str
    untrusted_content: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_id", _text("result.document_id", self.document_id, maximum=512))
        object.__setattr__(self, "chunk_id", _text("result.chunk_id", self.chunk_id, maximum=512))
        if not isinstance(self.score, (int, float)) or isinstance(self.score, bool) or self.score < 0:
            raise KnowledgeValidationError("result.score must be a non-negative number")
        object.__setattr__(self, "score", float(self.score))
        object.__setattr__(self, "text", _text("result.text", self.text, maximum=100_000))
        if not isinstance(self.source, KnowledgeSourceReference):
            raise KnowledgeValidationError("result.source must be a source reference")
        object.__setattr__(self, "content_hash", _text("result.content_hash", self.content_hash, maximum=256))
        if self.untrusted_content is not True:
            raise KnowledgeValidationError("retrieved content must remain marked untrusted")
