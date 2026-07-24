"""Dependency-free knowledge test adapter with deterministic lexical retrieval.

It is deliberately a local/reference adapter. Production deployments replace
the same ports with object storage, lexical search, vector retrieval, and graph
retrieval adapters while retaining the citation and tenant-boundary contracts.
"""

from __future__ import annotations

import hashlib
import re
from threading import RLock
from typing import Sequence

from ..application.knowledge import KnowledgeChunkerPort, KnowledgeStorePort
from ..domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeQuery,
    KnowledgeSearchResult,
    KnowledgeSourceReference,
)


_TOKEN_PATTERN = re.compile(r"[a-z0-9_]{2,}")


class ParagraphKnowledgeChunker(KnowledgeChunkerPort):
    """Deterministic paragraph/window chunker suitable for local verification only."""

    def __init__(self, *, maximum_characters: int = 1_500) -> None:
        if not 100 <= maximum_characters <= 20_000:
            raise ValueError("maximum_characters must be between 100 and 20000")
        self._maximum_characters = maximum_characters

    def chunk(self, document: KnowledgeDocument) -> Sequence[KnowledgeChunk]:
        paragraphs = [paragraph.strip() for paragraph in document.content.split("\n\n") if paragraph.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self._maximum_characters:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(
                    paragraph[index : index + self._maximum_characters]
                    for index in range(0, len(paragraph), self._maximum_characters)
                )
                continue
            if current and len(current) + 2 + len(paragraph) > self._maximum_characters:
                chunks.append(current)
                current = paragraph
            else:
                current = paragraph if not current else f"{current}\n\n{paragraph}"
        if current:
            chunks.append(current)
        if not chunks:
            chunks = [document.content]
        return tuple(
            KnowledgeChunk(
                chunk_id=f"{document.document_id}:chunk:{ordinal}",
                document_id=document.document_id,
                ordinal=ordinal,
                text=text.strip(),
                text_hash=f"sha256:{hashlib.sha256(text.strip().encode('utf-8')).hexdigest()}",
            )
            for ordinal, text in enumerate(chunks)
        )


class InMemoryKnowledgeStore(KnowledgeStorePort):
    """Thread-safe tenant-isolated reference store with source-aware content deduplication."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str, str], KnowledgeDocument] = {}
        self._chunks: dict[tuple[str, str, str], tuple[KnowledgeChunk, ...]] = {}
        self._lock = RLock()

    def upsert(
        self,
        document: KnowledgeDocument,
        chunks: Sequence[KnowledgeChunk],
    ) -> tuple[KnowledgeDocument, bool]:
        validated_chunks = tuple(chunks)
        if any(chunk.document_id != document.document_id for chunk in validated_chunks):
            raise ValueError("all chunks must belong to the upserted document")
        if not validated_chunks:
            raise ValueError("knowledge documents require at least one chunk")
        key = (document.tenant_id, document.workspace_id, document.content_hash)
        with self._lock:
            existing = self._documents.get(key)
            if existing is None:
                self._documents[key] = document
                self._chunks[key] = validated_chunks
                return document, False
            source_map: dict[tuple[str, str, str], KnowledgeSourceReference] = {
                source.identity: source for source in existing.sources
            }
            source_map.update({source.identity: source for source in document.sources})
            merged = KnowledgeDocument(
                document_id=existing.document_id,
                tenant_id=existing.tenant_id,
                workspace_id=existing.workspace_id,
                content_hash=existing.content_hash,
                title=existing.title,
                content=existing.content,
                content_type=existing.content_type,
                sources=tuple(sorted(source_map.values(), key=lambda source: source.identity)),
                metadata=existing.metadata,
                ingested_at=existing.ingested_at,
            )
            self._documents[key] = merged
            return merged, True

    def search(self, query: KnowledgeQuery) -> Sequence[KnowledgeSearchResult]:
        query_terms = frozenset(_TOKEN_PATTERN.findall(query.query.lower()))
        if not query_terms:
            return ()
        results: list[KnowledgeSearchResult] = []
        with self._lock:
            for (tenant_id, workspace_id, _), document in self._documents.items():
                if tenant_id != query.tenant_id or workspace_id != query.workspace_id:
                    continue
                qualifying_sources = tuple(
                    source for source in document.sources if source.trust_tier >= query.minimum_trust_tier
                )
                if not qualifying_sources:
                    continue
                citation_source = max(qualifying_sources, key=lambda source: int(source.trust_tier))
                for chunk in self._chunks[(tenant_id, workspace_id, document.content_hash)]:
                    chunk_terms = frozenset(_TOKEN_PATTERN.findall(chunk.text.lower()))
                    overlap = query_terms & chunk_terms
                    if not overlap:
                        continue
                    results.append(
                        KnowledgeSearchResult(
                            document_id=document.document_id,
                            chunk_id=chunk.chunk_id,
                            score=len(overlap) / len(query_terms),
                            text=chunk.text,
                            source=citation_source,
                            content_hash=document.content_hash,
                        )
                    )
        return tuple(
            sorted(results, key=lambda result: (-result.score, result.document_id, result.chunk_id))[
                : query.maximum_results
            ]
        )
