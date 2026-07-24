"""Knowledge ingestion and retrieval ports and services."""

from __future__ import annotations

import hashlib
from typing import Protocol, Sequence

from ..domain.events import new_event
from ..domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestRequest,
    KnowledgeQuery,
    KnowledgeSearchResult,
)
from .ports import EventPublisherPort


class KnowledgeChunkerPort(Protocol):
    """A replaceable tokenizer/chunker extension; may use language-aware logic."""

    def chunk(self, document: KnowledgeDocument) -> Sequence[KnowledgeChunk]:
        """Create deterministic bounded chunks for one immutable document."""


class KnowledgeStorePort(Protocol):
    """A tenant-isolated document/chunk store with source-reference deduplication."""

    def upsert(
        self,
        document: KnowledgeDocument,
        chunks: Sequence[KnowledgeChunk],
    ) -> tuple[KnowledgeDocument, bool]:
        """Persist document/chunks or merge provenance; return stored document and deduplication flag."""

    def search(self, query: KnowledgeQuery) -> Sequence[KnowledgeSearchResult]:
        """Return cited, tenant-isolated results using a backend-specific retrieval strategy."""


class KnowledgeIngestionService:
    """Content-address and ingest knowledge without allowing source text to execute instructions."""

    def __init__(self, store: KnowledgeStorePort, chunker: KnowledgeChunkerPort, events: EventPublisherPort) -> None:
        self._store = store
        self._chunker = chunker
        self._events = events

    def ingest(self, request: KnowledgeIngestRequest, *, correlation_id: str) -> KnowledgeDocument:
        """Create a versioned record, deduplicate content, and publish metadata-only audit evidence."""

        document = KnowledgeDocument(
            document_id=self._document_id(request),
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            content_hash=request.content_hash,
            title=request.title,
            content=request.content,
            content_type=request.content_type,
            sources=(request.source,),
            metadata=request.metadata,
        )
        chunks = self._chunker.chunk(document)
        stored, deduplicated = self._store.upsert(document, chunks)
        self._events.publish(
            new_event(
                event_type="knowledge.document.ingested.v1",
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                subject_id=stored.document_id,
                correlation_id=correlation_id,
                payload={
                    "content_hash": stored.content_hash,
                    "content_type": stored.content_type,
                    "deduplicated": deduplicated,
                    "source_count": len(stored.sources),
                    "chunk_count": len(chunks) if not deduplicated else None,
                    "effective_trust_tier": int(stored.effective_trust_tier),
                    "untrusted_content": stored.untrusted_content,
                },
            )
        )
        return stored

    @staticmethod
    def _document_id(request: KnowledgeIngestRequest) -> str:
        """Scope a deterministic content ID so equal tenant content cannot collide globally."""

        scope = f"{request.tenant_id}\x00{request.workspace_id}".encode("utf-8")
        scope_hash = hashlib.sha256(scope).hexdigest()[:24]
        return f"knowledge:{scope_hash}:{request.content_hash}"


class KnowledgeRetrievalService:
    """Read-only RAG retrieval service; callers must preserve result citations and trust labels."""

    def __init__(self, store: KnowledgeStorePort) -> None:
        self._store = store

    def search(self, query: KnowledgeQuery) -> tuple[KnowledgeSearchResult, ...]:
        """Return backend-ranked, cited chunks without modifying memory or knowledge state."""

        return tuple(self._store.search(query))
