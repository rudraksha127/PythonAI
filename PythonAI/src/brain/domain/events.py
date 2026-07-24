"""Versioned event envelope for ForgeAI's outbox and audit stream."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from .models import freeze_mapping, utc_now


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """An immutable integration event with traceability metadata."""

    event_id: str
    event_type: str
    occurred_at: datetime
    tenant_id: str
    workspace_id: str
    subject_id: str
    correlation_id: str
    schema_version: int
    payload: Mapping[str, Any] = field(default_factory=dict)
    causation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "event_type",
            "tenant_id",
            "workspace_id",
            "subject_id",
            "correlation_id",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.schema_version < 1:
            raise ValueError("schema_version must be at least 1")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "payload", freeze_mapping(self.payload))


def new_event(
    *,
    event_type: str,
    tenant_id: str,
    workspace_id: str,
    subject_id: str,
    correlation_id: str,
    payload: Mapping[str, Any] | None = None,
    causation_id: str | None = None,
    schema_version: int = 1,
) -> EventEnvelope:
    """Create an event with a generated identity and UTC timestamp."""

    return EventEnvelope(
        event_id=str(uuid4()),
        event_type=event_type,
        occurred_at=utc_now(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        subject_id=subject_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        schema_version=schema_version,
        payload=payload or {},
    )
