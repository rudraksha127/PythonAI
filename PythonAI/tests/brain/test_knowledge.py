from __future__ import annotations

import unittest

from src.brain.adapters.in_memory import InMemoryEventPublisher
from src.brain.adapters.in_memory_knowledge import InMemoryKnowledgeStore, ParagraphKnowledgeChunker
from src.brain.application.knowledge import KnowledgeIngestionService, KnowledgeRetrievalService
from src.brain.domain.knowledge import KnowledgeIngestRequest, KnowledgeQuery, KnowledgeSourceReference
from src.brain.domain.models import TrustTier


def request(
    *,
    tenant_id: str = "tenant-a",
    workspace_id: str = "workspace-a",
    source_id: str = "official-docs",
    source_version: str = "v1",
    trust_tier: TrustTier = TrustTier.OFFICIAL,
    content: str = "ForgeAI uses capability contracts.\n\nMCP metadata remains untrusted content.",
) -> KnowledgeIngestRequest:
    return KnowledgeIngestRequest(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        title="ForgeAI architecture",
        content=content,
        content_type="text/markdown",
        source=KnowledgeSourceReference(
            source_id=source_id,
            source_uri=f"https://docs.example.test/{source_id}",
            source_version=source_version,
            trust_tier=trust_tier,
        ),
    )


class KnowledgeKernelTests(unittest.TestCase):
    def test_content_hash_deduplicates_same_tenant_workspace_and_merges_versioned_provenance(self) -> None:
        store = InMemoryKnowledgeStore()
        events = InMemoryEventPublisher()
        service = KnowledgeIngestionService(store, ParagraphKnowledgeChunker(maximum_characters=100), events)

        first = service.ingest(request(), correlation_id="corr-first")
        second = service.ingest(
            request(source_id="release-notes", source_version="2026.07"),
            correlation_id="corr-second",
        )

        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(2, len(second.sources))
        self.assertTrue(second.untrusted_content)
        self.assertFalse(events.events()[0].payload["deduplicated"])
        self.assertTrue(events.events()[1].payload["deduplicated"])
        self.assertEqual(2, events.events()[1].payload["source_count"])

    def test_retrieval_is_tenant_workspace_and_trust_scoped_with_verifiable_citations(self) -> None:
        store = InMemoryKnowledgeStore()
        events = InMemoryEventPublisher()
        ingestion = KnowledgeIngestionService(store, ParagraphKnowledgeChunker(maximum_characters=100), events)
        retrieval = KnowledgeRetrievalService(store)
        official = ingestion.ingest(request(), correlation_id="corr-official")
        ingestion.ingest(
            request(
                tenant_id="tenant-b",
                workspace_id="workspace-b",
                source_id="other-tenant",
            ),
            correlation_id="corr-other",
        )
        ingestion.ingest(
            request(
                source_id="community-copy",
                source_version="v1",
                trust_tier=TrustTier.COMMUNITY,
                content="Community-only experimental connector guidance.",
            ),
            correlation_id="corr-community",
        )

        official_results = retrieval.search(
            KnowledgeQuery(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                query="capability MCP",
                minimum_trust_tier=TrustTier.OFFICIAL,
            )
        )
        other_results = retrieval.search(
            KnowledgeQuery(
                tenant_id="tenant-b",
                workspace_id="workspace-b",
                query="capability MCP",
                minimum_trust_tier=TrustTier.COMMUNITY,
            )
        )

        self.assertEqual(1, len(official_results))
        self.assertEqual(official.document_id, official_results[0].document_id)
        self.assertEqual(official.content_hash, official_results[0].content_hash)
        self.assertEqual("official-docs", official_results[0].source.source_id)
        self.assertTrue(official_results[0].untrusted_content)
        self.assertEqual(1, len(other_results))
        self.assertEqual("other-tenant", other_results[0].source.source_id)
        self.assertNotEqual(official_results[0].document_id, other_results[0].document_id)

    def test_content_is_chunked_and_never_written_verbatim_to_ingestion_audit_event(self) -> None:
        store = InMemoryKnowledgeStore()
        events = InMemoryEventPublisher()
        service = KnowledgeIngestionService(store, ParagraphKnowledgeChunker(maximum_characters=100), events)
        secret_text = "MCP research SECRET-DO-NOT-LOG. " * 20

        document = service.ingest(request(content=secret_text), correlation_id="corr-secret")
        results = KnowledgeRetrievalService(store).search(
            KnowledgeQuery(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                query="MCP research",
            )
        )

        self.assertTrue(document.document_id.startswith("knowledge:"))
        self.assertIn(":sha256:", document.document_id)
        self.assertGreater(len(results), 1)
        self.assertNotIn("SECRET-DO-NOT-LOG", str(dict(events.events()[0].payload)))
