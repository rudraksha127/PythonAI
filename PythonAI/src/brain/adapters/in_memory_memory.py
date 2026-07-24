"""Thread-safe local reference implementation of the hybrid-memory store port."""

from __future__ import annotations

import re
from threading import RLock
from typing import Sequence

from ..application.memory import MemoryStorePort
from ..domain.memory import MemoryQuery, MemoryRecord, MemorySearchResult


_TOKEN_PATTERN = re.compile(r"[a-z0-9_]{2,}")


class InMemoryMemoryStore(MemoryStorePort):
    """Deterministic lexical projection used for local tests; vector/graph stores share its port."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, str, str], MemoryRecord] = {}
        self._lock = RLock()

    def upsert(self, record: MemoryRecord) -> tuple[MemoryRecord, bool]:
        key = (
            record.tenant_id,
            record.workspace_id,
            record.scope.value,
            record.subject_id,
            record.content_hash,
        )
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                return existing, True
            self._records[key] = record
            return record, False

    def search(self, query: MemoryQuery) -> Sequence[MemorySearchResult]:
        query_tokens = frozenset(_TOKEN_PATTERN.findall(query.query.lower()))
        if not query_tokens:
            return ()
        results: list[MemorySearchResult] = []
        with self._lock:
            for record in self._records.values():
                if record.tenant_id != query.tenant_id or record.workspace_id != query.workspace_id:
                    continue
                if record.scope not in query.scopes or record.is_expired:
                    continue
                if query.subject_id is not None and record.subject_id != query.subject_id:
                    continue
                overlap = query_tokens & frozenset(_TOKEN_PATTERN.findall(record.content.lower()))
                if overlap:
                    results.append(MemorySearchResult(record=record, score=len(overlap) / len(query_tokens)))
        return tuple(
            sorted(results, key=lambda result: (-result.score, result.record.created_at, result.record.memory_id))[
                : query.maximum_results
            ]
        )
