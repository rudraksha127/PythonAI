"""Policy-bound memory write/read services and replaceable store port."""

from __future__ import annotations

from typing import Protocol, Sequence

from ..domain.events import new_event
from ..domain.memory import (
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    MemoryWriteRequest,
    new_memory_id,
)
from ..domain.models import PolicyAction, PolicyDecision, PolicyDecisionKind, PolicyRequest
from .ports import EventPublisherPort, PolicyEnginePort


class MemoryStorePort(Protocol):
    """Replaceable hybrid-memory storage and retrieval projection."""

    def upsert(self, record: MemoryRecord) -> tuple[MemoryRecord, bool]:
        """Persist a record or deduplicate it; return stored record and deduplication flag."""

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        """Return tenant-bound non-expired records ranked by backend-specific strategy."""


class MemoryPolicyBlocked(PermissionError):
    """Raised when default-deny policy blocks a memory operation."""

    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(f"memory policy blocked: {decision.kind.value} ({decision.reason_code})")
        self.decision = decision


class MemoryService:
    """Write/read memory through explicit policy actions while avoiding raw-content audit logs."""

    def __init__(self, store: MemoryStorePort, policy_engine: PolicyEnginePort, events: EventPublisherPort) -> None:
        self._store = store
        self._policy_engine = policy_engine
        self._events = events

    def write(
        self,
        request: MemoryWriteRequest,
        *,
        policy_request: PolicyRequest,
        correlation_id: str,
    ) -> MemoryRecord:
        """Policy-check and upsert a memory record; audit only hashes and metadata counts."""

        self._validate_policy_request(policy_request, request, PolicyAction.WRITE_MEMORY)
        decision = self._policy_engine.decide(policy_request)
        if not decision.permits_progress:
            raise MemoryPolicyBlocked(decision)
        record = MemoryRecord(
            memory_id=new_memory_id(),
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            scope=request.scope,
            subject_id=request.subject_id,
            content=request.content,
            content_hash=request.content_hash,
            provenance_id=request.provenance_id,
            source_kind=request.source_kind,
            tags=request.tags,
            sensitivity=request.sensitivity,
            expires_at=request.expires_at,
            metadata=request.metadata,
        )
        stored, deduplicated = self._store.upsert(record)
        self._events.publish(
            new_event(
                event_type="memory.record.written.v1",
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                subject_id=stored.memory_id,
                correlation_id=correlation_id,
                payload={
                    "scope": stored.scope.value,
                    "subject_id": stored.subject_id,
                    "content_hash": stored.content_hash,
                    "content_bytes": len(stored.content.encode("utf-8")),
                    "provenance_id": stored.provenance_id,
                    "source_kind": stored.source_kind,
                    "tag_count": len(stored.tags),
                    "sensitivity": stored.sensitivity.value,
                    "deduplicated": deduplicated,
                    "expires_at": stored.expires_at.isoformat() if stored.expires_at else None,
                    "policy": {
                        "decision": decision.kind.value,
                        "reason_code": decision.reason_code,
                        "policy_version": decision.policy_version,
                        "rule_id": decision.rule_id,
                    },
                },
            )
        )
        return stored

    def search(
        self,
        query: MemoryQuery,
        *,
        policy_request: PolicyRequest,
    ) -> tuple[MemorySearchResult, ...]:
        """Policy-check a read then delegate tenant-bound ranking to the configured store."""

        self._validate_policy_request(policy_request, query, PolicyAction.READ_MEMORY)
        decision = self._policy_engine.decide(policy_request)
        if not decision.permits_progress:
            raise MemoryPolicyBlocked(decision)
        return tuple(self._store.search(query))

    @staticmethod
    def _validate_policy_request(
        policy_request: PolicyRequest,
        value: MemoryWriteRequest | MemoryQuery,
        action: PolicyAction,
    ) -> None:
        if policy_request.action is not action:
            raise ValueError(f"memory operation requires policy action {action.value!r}")
        if policy_request.tenant_id != value.tenant_id or policy_request.workspace_id != value.workspace_id:
            raise ValueError("memory policy request tenant/workspace must match the memory operation")
        if policy_request.capability_id != f"memory:{action.value}":
            raise ValueError("memory policy request must use the scoped memory capability ID")
