"""The explicit dependency-injection composition root for local ForgeAI Brain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..adapters.in_memory import (
    DeclarativePolicyRule,
    DefaultDenyPolicyEngine,
    InMemoryCapabilityCatalog,
    InMemoryEventPublisher,
)
from ..adapters.sqlite_store import SqliteCapabilityStore
from ..adapters.in_memory_knowledge import InMemoryKnowledgeStore, ParagraphKnowledgeChunker
from ..application.services import CapabilityLifecycleService, CapabilityResolver
from ..application.mcp_installation import McpInstallationPlanningService
from ..application.mcp_probe import McpProbeSnapshotService
from ..application.ports import CapabilityCatalogPort, EventPublisherPort, PolicyEnginePort
from ..application.workflow_planning import WorkflowPlanner
from ..application.knowledge import KnowledgeIngestionService, KnowledgeRetrievalService, KnowledgeStorePort


@dataclass(slots=True)
class BrainContainer:
    """Wires port implementations without leaking infrastructure into use cases."""

    catalog: CapabilityCatalogPort
    policy_engine: PolicyEnginePort
    events: EventPublisherPort
    lifecycle: CapabilityLifecycleService
    resolver: CapabilityResolver
    mcp_installations: McpInstallationPlanningService
    mcp_probe_snapshots: McpProbeSnapshotService
    workflow_planner: WorkflowPlanner
    knowledge_store: KnowledgeStorePort
    knowledge_ingestion: KnowledgeIngestionService
    knowledge_retrieval: KnowledgeRetrievalService

    @classmethod
    def local(
        cls,
        rules: Sequence[DeclarativePolicyRule] = (),
        *,
        policy_version: str = "local-v1",
    ) -> "BrainContainer":
        catalog = InMemoryCapabilityCatalog()
        policy_engine = DefaultDenyPolicyEngine(rules, version=policy_version)
        events = InMemoryEventPublisher()
        knowledge_store = InMemoryKnowledgeStore()
        return cls(
            catalog=catalog,
            policy_engine=policy_engine,
            events=events,
            lifecycle=CapabilityLifecycleService(catalog, policy_engine, events),
            resolver=CapabilityResolver(catalog),
            mcp_installations=McpInstallationPlanningService(policy_engine, events),
            mcp_probe_snapshots=McpProbeSnapshotService(events),
            workflow_planner=WorkflowPlanner(CapabilityResolver(catalog), events),
            knowledge_store=knowledge_store,
            knowledge_ingestion=KnowledgeIngestionService(
                knowledge_store,
                ParagraphKnowledgeChunker(),
                events,
            ),
            knowledge_retrieval=KnowledgeRetrievalService(knowledge_store),
        )

    @classmethod
    def sqlite(
        cls,
        database_path: str | Path,
        rules: Sequence[DeclarativePolicyRule] = (),
        *,
        policy_version: str = "local-v1",
    ) -> "BrainContainer":
        """Wire a local durable catalog and transactional event outbox."""

        store = SqliteCapabilityStore(database_path)
        policy_engine = DefaultDenyPolicyEngine(rules, version=policy_version)
        knowledge_store = InMemoryKnowledgeStore()
        return cls(
            catalog=store,
            policy_engine=policy_engine,
            events=store,
            lifecycle=CapabilityLifecycleService(
                store,
                policy_engine,
                store,
                atomic_lifecycle=store,
            ),
            resolver=CapabilityResolver(store),
            mcp_installations=McpInstallationPlanningService(policy_engine, store),
            mcp_probe_snapshots=McpProbeSnapshotService(store),
            workflow_planner=WorkflowPlanner(CapabilityResolver(store), store),
            knowledge_store=knowledge_store,
            knowledge_ingestion=KnowledgeIngestionService(
                knowledge_store,
                ParagraphKnowledgeChunker(),
                store,
            ),
            knowledge_retrieval=KnowledgeRetrievalService(knowledge_store),
        )
