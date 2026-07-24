"""Ports that keep the application layer independent of concrete infrastructure."""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from ..domain.events import EventEnvelope
from ..domain.models import (
    CapabilityRecord,
    CapabilityStatus,
    PolicyDecision,
    PolicyRequest,
)


class CatalogConflict(RuntimeError):
    """Raised when an optimistic-concurrency update has become stale."""


class CapabilityCatalogPort(Protocol):
    """Durable catalog operations required by capability application services."""

    def create(self, record: CapabilityRecord) -> CapabilityRecord:
        """Persist a new candidate record."""

    def get(self, capability_id: str) -> CapabilityRecord | None:
        """Fetch the current record for a capability ID."""

    def list_records(self) -> Sequence[CapabilityRecord]:
        """List the current records without exposing mutable storage."""

    def transition(
        self,
        capability_id: str,
        *,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
    ) -> CapabilityRecord:
        """Perform a lifecycle transition using optimistic concurrency."""


class PolicyEnginePort(Protocol):
    """Policy decision point contract."""

    def decide(self, request: PolicyRequest) -> PolicyDecision:
        """Return an explainable policy decision."""


class EventPublisherPort(Protocol):
    """Outbox/event-bus abstraction."""

    def publish(self, event: EventEnvelope) -> None:
        """Persist or dispatch an event exactly once from the caller's view."""


CapabilityEventFactory = Callable[[CapabilityRecord], EventEnvelope]


class AtomicCapabilityLifecyclePort(Protocol):
    """Optional persistence seam for record-and-outbox atomicity.

    The normal catalog and publisher ports keep the kernel easy to test. A
    durable adapter can additionally implement this port so a successful
    lifecycle state write and its audit/outbox event commit together.
    """

    def create_with_event(self, record: CapabilityRecord, event: EventEnvelope) -> CapabilityRecord:
        """Create a record and write its event in one durable transaction."""

    def transition_with_event(
        self,
        capability_id: str,
        *,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
        event_factory: CapabilityEventFactory,
    ) -> CapabilityRecord:
        """Transition a record and write the event derived from its new revision atomically."""


class EventOutboxPort(EventPublisherPort, Protocol):
    """Durable outbox operations used by an asynchronous event dispatcher."""

    def pending_events(self, *, limit: int = 100) -> Sequence[EventEnvelope]:
        """Return unpublished events in deterministic order."""

    def mark_published(self, event_id: str) -> None:
        """Mark an already-delivered event as published idempotently."""
