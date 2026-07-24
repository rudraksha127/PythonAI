"""Capability resolution and lifecycle use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from ..domain.events import EventEnvelope, new_event
from ..domain.lifecycle import required_policy_action
from ..domain.models import (
    RISK_ORDER,
    CapabilityRecord,
    CapabilityRequirement,
    CapabilityStatus,
    PolicyAction,
    PolicyDecision,
    PolicyDecisionKind,
    PolicyRequest,
)
from .ports import (
    AtomicCapabilityLifecyclePort,
    CapabilityCatalogPort,
    EventPublisherPort,
    PolicyEnginePort,
)


class PolicyBlocked(PermissionError):
    """Raised when a policy decision prevents a capability state change."""

    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(f"policy blocked action: {decision.kind.value} ({decision.reason_code})")
        self.decision = decision


@dataclass(frozen=True, slots=True)
class ResolvedCapability:
    """A deterministic candidate selection result for a workflow planner."""

    record: CapabilityRecord
    score: tuple[int, int, str]


class CapabilityResolver:
    """Resolve requirements against active catalog entries without vendor logic."""

    def __init__(self, catalog: CapabilityCatalogPort) -> None:
        self._catalog = catalog

    def resolve(self, requirement: CapabilityRequirement) -> ResolvedCapability | None:
        matches = [
            record
            for record in self._catalog.list_records()
            if self._matches(requirement, record)
        ]
        if not matches:
            return None
        scored = sorted(
            ((self._score(record), record) for record in matches),
            key=lambda item: item[0],
            reverse=True,
        )
        score, record = scored[0]
        return ResolvedCapability(record=record, score=score)

    @staticmethod
    def _matches(requirement: CapabilityRequirement, record: CapabilityRecord) -> bool:
        descriptor = record.descriptor
        if record.status is not CapabilityStatus.ACTIVE:
            return False
        if requirement.capability_ids and descriptor.capability_id not in requirement.capability_ids:
            return False
        if requirement.kind is not None and descriptor.kind != requirement.kind:
            return False
        if not requirement.required_tags.issubset(descriptor.tags):
            return False
        if descriptor.risk_level not in requirement.allowed_risk_levels:
            return False
        return record.candidate.trust_tier >= requirement.minimum_trust_tier

    @staticmethod
    def _score(record: CapabilityRecord) -> tuple[int, int, str]:
        # Higher provenance is preferred; lower operational risk breaks ties.
        return (
            int(record.candidate.trust_tier),
            -RISK_ORDER[record.descriptor.risk_level],
            record.capability_id,
        )


class CapabilityLifecycleService:
    """Apply policy before every durable, side-effecting lifecycle advance."""

    def __init__(
        self,
        catalog: CapabilityCatalogPort,
        policy_engine: PolicyEnginePort,
        events: EventPublisherPort,
        *,
        atomic_lifecycle: AtomicCapabilityLifecyclePort | None = None,
    ) -> None:
        self._catalog = catalog
        self._policy_engine = policy_engine
        self._events = events
        self._atomic_lifecycle = atomic_lifecycle

    def register(
        self,
        record: CapabilityRecord,
        *,
        tenant_id: str,
        workspace_id: str,
        correlation_id: str,
    ) -> CapabilityRecord:
        """Register an observed candidate and record its provenance event."""

        event = new_event(
            event_type="capability.registered.v1",
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            subject_id=record.capability_id,
            correlation_id=correlation_id,
            payload={
                "candidate_id": record.candidate.candidate_id,
                "source_name": record.candidate.source_name,
                "trust_tier": int(record.candidate.trust_tier),
                "artifact": {
                    "kind": record.candidate.artifact.kind,
                    "locator": record.candidate.artifact.locator,
                    "version": record.candidate.artifact.version,
                    "digest": record.candidate.artifact.digest,
                },
            },
        )
        if self._atomic_lifecycle is not None:
            return self._atomic_lifecycle.create_with_event(record, event)
        created = self._catalog.create(record)
        self._events.publish(event)
        return created

    def advance(
        self,
        *,
        capability_id: str,
        expected_revision: int,
        target: CapabilityStatus,
        action: PolicyAction | None,
        request: PolicyRequest | None,
        reason: str,
        tenant_id: str,
        workspace_id: str,
        correlation_id: str,
    ) -> CapabilityRecord:
        """Evaluate policy, apply an optimistic transition, and emit an event."""

        current = self._catalog.get(capability_id)
        if current is None:
            raise KeyError(f"unknown capability {capability_id!r}")
        if not tenant_id.strip() or not workspace_id.strip():
            raise ValueError("all lifecycle transitions require tenant and workspace context")
        expected_action = required_policy_action(current.status, target)
        if expected_action is None:
            if action is not None or request is not None:
                raise ValueError("safety transitions may not carry a policy action or request")
            return self._transition_and_publish(
                capability_id=capability_id,
                expected_revision=expected_revision,
                target=target,
                reason=reason,
                event_factory=lambda updated: new_event(
                    event_type="capability.safety_transitioned.v1",
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    subject_id=updated.capability_id,
                    correlation_id=correlation_id,
                    payload={
                        "previous_status": current.status.value,
                        "target_status": updated.status.value,
                        "revision": updated.revision,
                        "reason": reason,
                    },
                ),
            )
        if action is not expected_action:
            raise ValueError(
                f"transition from {current.status.value!r} to {target.value!r} "
                f"requires policy action {expected_action.value!r}"
            )
        if request is None:
            raise ValueError("a policy-governed transition requires a policy request")
        if request.tenant_id != tenant_id or request.workspace_id != workspace_id:
            raise ValueError("policy request tenant and workspace must match the audit context")
        if request.capability_id != capability_id:
            raise ValueError("policy request must refer to the transitioned capability")
        if request.action is not action:
            raise ValueError("policy request action must match the requested lifecycle action")
        decision = self._policy_engine.decide(request)
        if not decision.permits_progress:
            raise PolicyBlocked(decision)
        if decision.kind is PolicyDecisionKind.REQUIRE_SANDBOX and not request.sandboxed:
            raise PolicyBlocked(
                PolicyDecision(
                    kind=PolicyDecisionKind.DENY,
                    reason_code="sandbox-required",
                    policy_version=decision.policy_version,
                    rule_id=decision.rule_id,
                    obligations=decision.obligations,
                )
            )
        return self._transition_and_publish(
            capability_id=capability_id,
            expected_revision=expected_revision,
            target=target,
            reason=reason,
            event_factory=lambda updated: new_event(
                event_type="capability.transitioned.v1",
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                subject_id=updated.capability_id,
                correlation_id=correlation_id,
                payload={
                    "action": action.value,
                    "target_status": updated.status.value,
                    "revision": updated.revision,
                    "reason": reason,
                    "policy": {
                        "decision": decision.kind.value,
                        "reason_code": decision.reason_code,
                        "policy_version": decision.policy_version,
                        "rule_id": decision.rule_id,
                    },
                },
            ),
        )

    def _transition_and_publish(
        self,
        *,
        capability_id: str,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
        event_factory: Callable[[CapabilityRecord], EventEnvelope],
    ) -> CapabilityRecord:
        """Use an atomic store when supplied, otherwise retain the simple port path."""

        if self._atomic_lifecycle is not None:
            return self._atomic_lifecycle.transition_with_event(
                capability_id,
                expected_revision=expected_revision,
                target=target,
                reason=reason,
                event_factory=event_factory,
            )
        updated = self._catalog.transition(
            capability_id,
            expected_revision=expected_revision,
            target=target,
            reason=reason,
        )
        self._events.publish(event_factory(updated))
        return updated


def active_records(records: Iterable[CapabilityRecord]) -> tuple[CapabilityRecord, ...]:
    """Small reusable projection for adapters that need only active capabilities."""

    return tuple(record for record in records if record.status is CapabilityStatus.ACTIVE)
