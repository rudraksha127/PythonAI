"""SQLite-backed capability catalog and transactional outbox adapter.

SQLite is the local-first durable implementation. It keeps a capability write
and its lifecycle event in the same database transaction when used through
``AtomicCapabilityLifecyclePort``. Production multi-node deployments can swap
this adapter for PostgreSQL without changing application use cases.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Mapping, Sequence

from ..application.ports import CapabilityEventFactory, CatalogConflict
from ..domain.events import EventEnvelope
from ..domain.lifecycle import transition
from ..domain.models import (
    ArtifactReference,
    CapabilityCandidate,
    CapabilityDescriptor,
    CapabilityRecord,
    CapabilityStatus,
    PluginManifest,
    PluginRuntime,
    RiskLevel,
    TrustTier,
)
from ..domain.models import utc_now


class SqliteStoreError(RuntimeError):
    """Raised for corrupted persisted data or an unavailable local store."""


def _json_value(value: Any) -> Any:
    """Convert immutable domain metadata to JSON without weakening its validation."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_value(item) for item in value)
    return value


def _canonical_json(value: Mapping[str, Any], field_name: str) -> str:
    try:
        return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise SqliteStoreError(f"{field_name} is not JSON-serializable") from error


def _object(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SqliteStoreError(f"persisted {field_name} must be an object")
    return value


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SqliteStoreError(f"persisted {field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SqliteStoreError(f"persisted {field_name} must be an array of strings")
    return value


def _timestamp(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        result = datetime.fromisoformat(text)
    except ValueError as error:
        raise SqliteStoreError(f"persisted {field_name} must be an ISO-8601 timestamp") from error
    if result.tzinfo is None:
        raise SqliteStoreError(f"persisted {field_name} must be timezone-aware")
    return result


def _artifact_payload(artifact: ArtifactReference) -> dict[str, Any]:
    return {
        "kind": artifact.kind,
        "locator": artifact.locator,
        "version": artifact.version,
        "digest": artifact.digest,
    }


def _artifact_from_payload(value: Any, field_name: str) -> ArtifactReference:
    payload = _object(value, field_name)
    return ArtifactReference(
        kind=_text(payload.get("kind"), f"{field_name}.kind"),
        locator=_text(payload.get("locator"), f"{field_name}.locator"),
        version=_text(payload.get("version"), f"{field_name}.version"),
        digest=_optional_text(payload.get("digest"), f"{field_name}.digest"),
    )


def _record_payload(record: CapabilityRecord) -> dict[str, Any]:
    descriptor = record.descriptor
    candidate = record.candidate
    manifest = record.manifest
    return {
        "descriptor": {
            "capability_id": descriptor.capability_id,
            "version": descriptor.version,
            "name": descriptor.name,
            "description": descriptor.description,
            "kind": descriptor.kind,
            "risk_level": descriptor.risk_level.value,
            "tags": sorted(descriptor.tags),
            "required_permissions": sorted(descriptor.required_permissions),
            "input_schema": descriptor.input_schema,
            "output_schema": descriptor.output_schema,
            "metadata": descriptor.metadata,
        },
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "capability_id": candidate.capability_id,
            "source_name": candidate.source_name,
            "source_url": candidate.source_url,
            "trust_tier": int(candidate.trust_tier),
            "artifact": _artifact_payload(candidate.artifact),
            "raw_metadata_hash": candidate.raw_metadata_hash,
            "observed_at": candidate.observed_at.isoformat(),
            "metadata": candidate.metadata,
        },
        "manifest": {
            "plugin_id": manifest.plugin_id,
            "version": manifest.version,
            "publisher": manifest.publisher,
            "kind": manifest.kind,
            "runtime": manifest.runtime.value,
            "entrypoint": manifest.entrypoint,
            "provided_capability_ids": list(manifest.provided_capability_ids),
            "requested_permissions": sorted(manifest.requested_permissions),
            "api_version": manifest.api_version,
            "compatibility": manifest.compatibility,
            "metadata": manifest.metadata,
        },
        "status": record.status.value,
        "revision": record.revision,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "last_transition_reason": record.last_transition_reason,
    }


def _record_from_payload(value: Any) -> CapabilityRecord:
    try:
        payload = _object(value, "capability record")
        descriptor_value = _object(payload.get("descriptor"), "capability record.descriptor")
        candidate_value = _object(payload.get("candidate"), "capability record.candidate")
        manifest_value = _object(payload.get("manifest"), "capability record.manifest")
        descriptor = CapabilityDescriptor(
            capability_id=_text(descriptor_value.get("capability_id"), "descriptor.capability_id"),
            version=_text(descriptor_value.get("version"), "descriptor.version"),
            name=_text(descriptor_value.get("name"), "descriptor.name"),
            description=_text(descriptor_value.get("description"), "descriptor.description"),
            kind=_text(descriptor_value.get("kind"), "descriptor.kind"),
            risk_level=RiskLevel(_text(descriptor_value.get("risk_level"), "descriptor.risk_level")),
            tags=frozenset(_string_list(descriptor_value.get("tags"), "descriptor.tags")),
            required_permissions=frozenset(
                _string_list(descriptor_value.get("required_permissions"), "descriptor.required_permissions")
            ),
            input_schema=_object(descriptor_value.get("input_schema"), "descriptor.input_schema"),
            output_schema=_object(descriptor_value.get("output_schema"), "descriptor.output_schema"),
            metadata=_object(descriptor_value.get("metadata"), "descriptor.metadata"),
        )
        candidate = CapabilityCandidate(
            candidate_id=_text(candidate_value.get("candidate_id"), "candidate.candidate_id"),
            capability_id=_text(candidate_value.get("capability_id"), "candidate.capability_id"),
            source_name=_text(candidate_value.get("source_name"), "candidate.source_name"),
            source_url=_text(candidate_value.get("source_url"), "candidate.source_url"),
            trust_tier=TrustTier(candidate_value.get("trust_tier")),
            artifact=_artifact_from_payload(candidate_value.get("artifact"), "candidate.artifact"),
            raw_metadata_hash=_text(candidate_value.get("raw_metadata_hash"), "candidate.raw_metadata_hash"),
            observed_at=_timestamp(candidate_value.get("observed_at"), "candidate.observed_at"),
            metadata=_object(candidate_value.get("metadata"), "candidate.metadata"),
        )
        manifest = PluginManifest(
            plugin_id=_text(manifest_value.get("plugin_id"), "manifest.plugin_id"),
            version=_text(manifest_value.get("version"), "manifest.version"),
            publisher=_text(manifest_value.get("publisher"), "manifest.publisher"),
            kind=_text(manifest_value.get("kind"), "manifest.kind"),
            runtime=PluginRuntime(_text(manifest_value.get("runtime"), "manifest.runtime")),
            entrypoint=_text(manifest_value.get("entrypoint"), "manifest.entrypoint"),
            provided_capability_ids=tuple(
                _string_list(manifest_value.get("provided_capability_ids"), "manifest.provided_capability_ids")
            ),
            requested_permissions=frozenset(
                _string_list(manifest_value.get("requested_permissions"), "manifest.requested_permissions")
            ),
            api_version=_text(manifest_value.get("api_version"), "manifest.api_version"),
            compatibility=_object(manifest_value.get("compatibility"), "manifest.compatibility"),
            metadata=_object(manifest_value.get("metadata"), "manifest.metadata"),
        )
        revision = payload.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise SqliteStoreError("persisted record.revision must be an integer")
        return CapabilityRecord(
            descriptor=descriptor,
            candidate=candidate,
            manifest=manifest,
            status=CapabilityStatus(_text(payload.get("status"), "record.status")),
            revision=revision,
            created_at=_timestamp(payload.get("created_at"), "record.created_at"),
            updated_at=_timestamp(payload.get("updated_at"), "record.updated_at"),
            last_transition_reason=_optional_text(
                payload.get("last_transition_reason"), "record.last_transition_reason"
            ),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, SqliteStoreError):
            raise
        raise SqliteStoreError("persisted capability record violates the domain contract") from error


def _event_payload(event: EventEnvelope) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "tenant_id": event.tenant_id,
        "workspace_id": event.workspace_id,
        "subject_id": event.subject_id,
        "correlation_id": event.correlation_id,
        "schema_version": event.schema_version,
        "payload": event.payload,
        "causation_id": event.causation_id,
    }


def _event_from_payload(value: Any) -> EventEnvelope:
    try:
        payload = _object(value, "event")
        schema_version = payload.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise SqliteStoreError("persisted event.schema_version must be an integer")
        return EventEnvelope(
            event_id=_text(payload.get("event_id"), "event.event_id"),
            event_type=_text(payload.get("event_type"), "event.event_type"),
            occurred_at=_timestamp(payload.get("occurred_at"), "event.occurred_at"),
            tenant_id=_text(payload.get("tenant_id"), "event.tenant_id"),
            workspace_id=_text(payload.get("workspace_id"), "event.workspace_id"),
            subject_id=_text(payload.get("subject_id"), "event.subject_id"),
            correlation_id=_text(payload.get("correlation_id"), "event.correlation_id"),
            schema_version=schema_version,
            payload=_object(payload.get("payload"), "event.payload"),
            causation_id=_optional_text(payload.get("causation_id"), "event.causation_id"),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, SqliteStoreError):
            raise
        raise SqliteStoreError("persisted event violates the domain contract") from error


class SqliteCapabilityStore:
    """Local durable catalog, transactional outbox, and atomic lifecycle adapter."""

    def __init__(self, database_path: str | Path) -> None:
        path = str(database_path)
        if not path.strip():
            raise ValueError("database_path must be non-empty")
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._database_path = path
        self._connection = sqlite3.connect(
            path,
            check_same_thread=False,
            isolation_level="DEFERRED",
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._closed = False
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = NORMAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS capability_catalog (
                    capability_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS event_outbox (
                    event_id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    published_at TEXT NULL
                );
                CREATE INDEX IF NOT EXISTS event_outbox_pending_idx
                    ON event_outbox (published_at, occurred_at, event_id);
                """
            )

    @property
    def database_path(self) -> str:
        """Configured SQLite path, useful for local operational diagnostics."""

        return self._database_path

    def close(self) -> None:
        """Close the underlying SQLite handle; a closed store cannot be reused."""

        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def create(self, record: CapabilityRecord) -> CapabilityRecord:
        with self._lock, self._connection:
            self._ensure_open()
            self._insert_record(record)
            return record

    def get(self, capability_id: str) -> CapabilityRecord | None:
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT record_json FROM capability_catalog WHERE capability_id = ?", (capability_id,)
            ).fetchone()
            return None if row is None else self._decode_record(row["record_json"])

    def list_records(self) -> Sequence[CapabilityRecord]:
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                "SELECT record_json FROM capability_catalog ORDER BY capability_id"
            ).fetchall()
            return tuple(self._decode_record(row["record_json"]) for row in rows)

    def transition(
        self,
        capability_id: str,
        *,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
    ) -> CapabilityRecord:
        with self._lock, self._connection:
            self._ensure_open()
            return self._transition_record(
                capability_id,
                expected_revision=expected_revision,
                target=target,
                reason=reason,
            )

    def create_with_event(self, record: CapabilityRecord, event: EventEnvelope) -> CapabilityRecord:
        with self._lock, self._connection:
            self._ensure_open()
            self._insert_record(record)
            self._insert_event(event)
            return record

    def transition_with_event(
        self,
        capability_id: str,
        *,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
        event_factory: CapabilityEventFactory,
    ) -> CapabilityRecord:
        with self._lock, self._connection:
            self._ensure_open()
            updated = self._transition_record(
                capability_id,
                expected_revision=expected_revision,
                target=target,
                reason=reason,
            )
            event = event_factory(updated)
            if not isinstance(event, EventEnvelope):
                raise SqliteStoreError("atomic lifecycle event factory must return an EventEnvelope")
            self._insert_event(event)
            return updated

    def publish(self, event: EventEnvelope) -> None:
        with self._lock, self._connection:
            self._ensure_open()
            self._insert_event(event)

    def pending_events(self, *, limit: int = 100) -> Sequence[EventEnvelope]:
        if not 1 <= limit <= 1_000:
            raise ValueError("outbox limit must be between 1 and 1000")
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT event_json FROM event_outbox
                WHERE published_at IS NULL
                ORDER BY rowid
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return tuple(self._decode_event(row["event_json"]) for row in rows)

    def mark_published(self, event_id: str) -> None:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        with self._lock, self._connection:
            self._ensure_open()
            self._connection.execute(
                """
                UPDATE event_outbox
                SET published_at = ?
                WHERE event_id = ? AND published_at IS NULL
                """,
                (utc_now().isoformat(), event_id),
            )

    def _transition_record(
        self,
        capability_id: str,
        *,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
    ) -> CapabilityRecord:
        row = self._connection.execute(
            "SELECT revision, record_json FROM capability_catalog WHERE capability_id = ?", (capability_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown capability {capability_id!r}")
        if row["revision"] != expected_revision:
            raise CatalogConflict(
                f"stale revision for {capability_id!r}: expected {expected_revision}, found {row['revision']}"
            )
        updated = transition(self._decode_record(row["record_json"]), target, reason=reason)
        cursor = self._connection.execute(
            """
            UPDATE capability_catalog
            SET revision = ?, record_json = ?, updated_at = ?
            WHERE capability_id = ? AND revision = ?
            """,
            (
                updated.revision,
                _canonical_json(_record_payload(updated), "capability record"),
                updated.updated_at.isoformat(),
                capability_id,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise CatalogConflict(f"stale revision for {capability_id!r}")
        return updated

    def _insert_record(self, record: CapabilityRecord) -> None:
        try:
            self._connection.execute(
                """
                INSERT INTO capability_catalog (capability_id, revision, record_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.capability_id,
                    record.revision,
                    _canonical_json(_record_payload(record), "capability record"),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise CatalogConflict(f"capability {record.capability_id!r} already exists") from error

    def _insert_event(self, event: EventEnvelope) -> None:
        encoded = _canonical_json(_event_payload(event), "event")
        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO event_outbox (event_id, occurred_at, event_json, published_at)
            VALUES (?, ?, ?, NULL)
            """,
            (event.event_id, event.occurred_at.isoformat(), encoded),
        )
        if cursor.rowcount == 0:
            row = self._connection.execute(
                "SELECT event_json FROM event_outbox WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if row is None or row["event_json"] != encoded:
                raise SqliteStoreError(f"event ID collision for {event.event_id!r}")

    @staticmethod
    def _decode_record(encoded: str) -> CapabilityRecord:
        try:
            return _record_from_payload(json.loads(encoded))
        except json.JSONDecodeError as error:
            raise SqliteStoreError("persisted capability record is not valid JSON") from error

    @staticmethod
    def _decode_event(encoded: str) -> EventEnvelope:
        try:
            return _event_from_payload(json.loads(encoded))
        except json.JSONDecodeError as error:
            raise SqliteStoreError("persisted event is not valid JSON") from error

    def _ensure_open(self) -> None:
        if self._closed:
            raise SqliteStoreError("SQLite capability store is closed")
