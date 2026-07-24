"""Capability lifecycle invariants independent of persistence or policy engines."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Mapping

from .models import CapabilityRecord, CapabilityStatus, PolicyAction, utc_now


class CapabilityLifecycleError(ValueError):
    """Raised when a state transition would violate lifecycle invariants."""


ALLOWED_TRANSITIONS: Mapping[CapabilityStatus, frozenset[CapabilityStatus]] = MappingProxyType(
    {
        CapabilityStatus.CANDIDATE: frozenset(
            {CapabilityStatus.VALIDATED, CapabilityStatus.QUARANTINED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.VALIDATED: frozenset(
            {CapabilityStatus.APPROVED, CapabilityStatus.QUARANTINED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.APPROVED: frozenset(
            {CapabilityStatus.INSTALLING, CapabilityStatus.QUARANTINED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.INSTALLING: frozenset(
            {CapabilityStatus.INSTALLED, CapabilityStatus.QUARANTINED, CapabilityStatus.DEGRADED}
        ),
        CapabilityStatus.INSTALLED: frozenset(
            {CapabilityStatus.PROBING, CapabilityStatus.QUARANTINED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.PROBING: frozenset(
            {CapabilityStatus.ACTIVE, CapabilityStatus.DEGRADED, CapabilityStatus.QUARANTINED}
        ),
        CapabilityStatus.ACTIVE: frozenset(
            {CapabilityStatus.DEGRADED, CapabilityStatus.QUARANTINED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.DEGRADED: frozenset(
            {CapabilityStatus.ACTIVE, CapabilityStatus.QUARANTINED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.QUARANTINED: frozenset(
            {CapabilityStatus.VALIDATED, CapabilityStatus.RETIRED}
        ),
        CapabilityStatus.RETIRED: frozenset(),
    }
)

# Only state changes that can introduce or execute an external capability need
# a PDP decision. Safety transitions (degrade, quarantine, retire) must remain
# available to a health monitor even when a policy service is unavailable.
TRANSITION_POLICY_ACTIONS: Mapping[
    tuple[CapabilityStatus, CapabilityStatus], PolicyAction
] = MappingProxyType(
    {
        (CapabilityStatus.CANDIDATE, CapabilityStatus.VALIDATED): PolicyAction.DISCOVER,
        (CapabilityStatus.VALIDATED, CapabilityStatus.APPROVED): PolicyAction.INSTALL,
        (CapabilityStatus.APPROVED, CapabilityStatus.INSTALLING): PolicyAction.INSTALL,
        (CapabilityStatus.INSTALLING, CapabilityStatus.INSTALLED): PolicyAction.INSTALL,
        (CapabilityStatus.INSTALLED, CapabilityStatus.PROBING): PolicyAction.ACTIVATE,
        (CapabilityStatus.PROBING, CapabilityStatus.ACTIVE): PolicyAction.ACTIVATE,
        (CapabilityStatus.DEGRADED, CapabilityStatus.ACTIVE): PolicyAction.ACTIVATE,
        (CapabilityStatus.QUARANTINED, CapabilityStatus.VALIDATED): PolicyAction.DISCOVER,
    }
)


def can_transition(current: CapabilityStatus, target: CapabilityStatus) -> bool:
    """Return whether the supplied transition is an allowed state change."""

    return target in ALLOWED_TRANSITIONS[current]


def required_policy_action(
    current: CapabilityStatus,
    target: CapabilityStatus,
) -> PolicyAction | None:
    """Return the only policy action permitted for a lifecycle transition."""

    return TRANSITION_POLICY_ACTIONS.get((current, target))


def transition(
    record: CapabilityRecord,
    target: CapabilityStatus,
    *,
    reason: str,
) -> CapabilityRecord:
    """Create the next immutable record after validating its state transition."""

    if not reason or not reason.strip():
        raise CapabilityLifecycleError("a lifecycle transition requires a reason")
    if not can_transition(record.status, target):
        raise CapabilityLifecycleError(
            f"cannot transition {record.capability_id!r} from {record.status.value!r} "
            f"to {target.value!r}"
        )
    return replace(
        record,
        status=target,
        revision=record.revision + 1,
        updated_at=utc_now(),
        last_transition_reason=reason.strip(),
    )
