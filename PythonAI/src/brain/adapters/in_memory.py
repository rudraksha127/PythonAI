"""Deterministic local adapters used by tests and the first composition root."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Sequence

from ..application.ports import CatalogConflict
from ..domain.events import EventEnvelope
from ..domain.lifecycle import transition
from ..domain.models import (
    RISK_ORDER,
    CapabilityRecord,
    CapabilityStatus,
    PolicyAction,
    PolicyDecision,
    PolicyDecisionKind,
    PolicyRequest,
    RiskLevel,
    TrustTier,
)


class InMemoryCapabilityCatalog:
    """Thread-safe reference catalog with optimistic-concurrency semantics."""

    def __init__(self) -> None:
        self._records: dict[str, CapabilityRecord] = {}
        self._lock = RLock()

    def create(self, record: CapabilityRecord) -> CapabilityRecord:
        with self._lock:
            if record.capability_id in self._records:
                raise CatalogConflict(f"capability {record.capability_id!r} already exists")
            self._records[record.capability_id] = record
            return record

    def get(self, capability_id: str) -> CapabilityRecord | None:
        with self._lock:
            return self._records.get(capability_id)

    def list_records(self) -> Sequence[CapabilityRecord]:
        with self._lock:
            return tuple(self._records.values())

    def transition(
        self,
        capability_id: str,
        *,
        expected_revision: int,
        target: CapabilityStatus,
        reason: str,
    ) -> CapabilityRecord:
        with self._lock:
            record = self._records.get(capability_id)
            if record is None:
                raise KeyError(f"unknown capability {capability_id!r}")
            if record.revision != expected_revision:
                raise CatalogConflict(
                    f"stale revision for {capability_id!r}: expected {expected_revision}, "
                    f"found {record.revision}"
                )
            updated = transition(record, target, reason=reason)
            self._records[capability_id] = updated
            return updated


class InMemoryEventPublisher:
    """Append-only event sink that mirrors a transactional outbox's public port."""

    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []
        self._lock = RLock()

    def publish(self, event: EventEnvelope) -> None:
        with self._lock:
            if any(existing.event_id == event.event_id for existing in self._events):
                return
            self._events.append(event)

    def events(self) -> tuple[EventEnvelope, ...]:
        with self._lock:
            return tuple(self._events)


@dataclass(frozen=True, slots=True)
class DeclarativePolicyRule:
    """A small deterministic rule format; production OPA/Cedar adapters share this port."""

    rule_id: str
    effect: PolicyDecisionKind
    actions: frozenset[PolicyAction]
    priority: int = 100
    principal_ids: frozenset[str] = field(default_factory=frozenset)
    capability_ids: frozenset[str] = field(default_factory=frozenset)
    minimum_trust_tier: TrustTier = TrustTier.UNTRUSTED
    maximum_risk_level: RiskLevel = RiskLevel.CRITICAL
    allowed_permissions: frozenset[str] | None = None
    requires_sandbox: bool = False
    reason_code: str = "rule-matched"

    def __post_init__(self) -> None:
        if not self.rule_id or not self.rule_id.strip():
            raise ValueError("rule_id must be non-empty")
        if not self.actions:
            raise ValueError("policy rule must apply to at least one action")
        if self.allowed_permissions is not None and any(
            not permission.strip() for permission in self.allowed_permissions
        ):
            raise ValueError("allowed_permissions may not contain blank values")

    def matches(self, request: PolicyRequest) -> bool:
        if request.action not in self.actions:
            return False
        if self.principal_ids and request.principal_id not in self.principal_ids:
            return False
        if self.capability_ids and request.capability_id not in self.capability_ids:
            return False
        if request.trust_tier < self.minimum_trust_tier:
            return False
        if RISK_ORDER[request.risk_level] > RISK_ORDER[self.maximum_risk_level]:
            return False
        if self.allowed_permissions is not None and not request.requested_permissions.issubset(
            self.allowed_permissions
        ):
            return False
        return True


class DefaultDenyPolicyEngine:
    """Policy engine with deterministic precedence and a fail-closed default."""

    def __init__(self, rules: Sequence[DeclarativePolicyRule] = (), *, version: str = "local-v1") -> None:
        if not version or not version.strip():
            raise ValueError("policy version must be non-empty")
        self._version = version
        self._rules = tuple(
            sorted(
                rules,
                key=lambda rule: (rule.priority, self._effect_precedence(rule.effect)),
                reverse=True,
            )
        )

    @staticmethod
    def _effect_precedence(effect: PolicyDecisionKind) -> int:
        return {
            PolicyDecisionKind.DENY: 4,
            PolicyDecisionKind.REQUIRE_APPROVAL: 3,
            PolicyDecisionKind.REQUIRE_SANDBOX: 2,
            PolicyDecisionKind.ALLOW: 1,
        }[effect]

    def decide(self, request: PolicyRequest) -> PolicyDecision:
        for rule in self._rules:
            if not rule.matches(request):
                continue
            if rule.requires_sandbox and not request.sandboxed:
                return PolicyDecision(
                    kind=PolicyDecisionKind.REQUIRE_SANDBOX,
                    reason_code=rule.reason_code,
                    policy_version=self._version,
                    rule_id=rule.rule_id,
                    obligations={"sandbox": True},
                )
            return PolicyDecision(
                kind=rule.effect,
                reason_code=rule.reason_code,
                policy_version=self._version,
                rule_id=rule.rule_id,
                obligations={"sandbox": rule.requires_sandbox} if rule.requires_sandbox else {},
            )
        return PolicyDecision(
            kind=PolicyDecisionKind.DENY,
            reason_code="no-matching-policy-rule",
            policy_version=self._version,
        )
