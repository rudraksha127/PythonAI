from __future__ import annotations

import unittest

from src.brain.adapters.in_memory import DeclarativePolicyRule
from src.brain.application.ports import CatalogConflict
from src.brain.application.services import PolicyBlocked
from src.brain.domain.models import (
    CapabilityStatus,
    PolicyAction,
    PolicyDecisionKind,
    PolicyRequest,
    RiskLevel,
    TrustTier,
)
from src.brain.runtime.container import BrainContainer

from .helpers import record


def request(
    capability_id: str,
    *,
    action: PolicyAction = PolicyAction.DISCOVER,
    sandboxed: bool = False,
) -> PolicyRequest:
    return PolicyRequest(
        action=action,
        principal_id="forgeai-automation",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        capability_id=capability_id,
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
        requested_permissions=frozenset({"network:egress:docs.example.test"}),
        automated=True,
        sandboxed=sandboxed,
    )


class CatalogAndPolicyTests(unittest.TestCase):
    def test_default_deny_blocks_lifecycle_progress(self) -> None:
        brain = BrainContainer.local()
        candidate = brain.lifecycle.register(
            record(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="correlation-a",
        )

        with self.assertRaises(PolicyBlocked) as error:
            brain.lifecycle.advance(
                capability_id=candidate.capability_id,
                expected_revision=candidate.revision,
                target=CapabilityStatus.VALIDATED,
                action=PolicyAction.DISCOVER,
                request=request(candidate.capability_id),
                reason="static validation passed",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="correlation-a",
            )

        self.assertEqual(PolicyDecisionKind.DENY, error.exception.decision.kind)
        self.assertEqual(CapabilityStatus.CANDIDATE, brain.catalog.get(candidate.capability_id).status)

    def test_policy_gated_transition_emits_versioned_audit_event(self) -> None:
        rule = DeclarativePolicyRule(
            rule_id="permit-official-low-risk-install",
            effect=PolicyDecisionKind.ALLOW,
            actions=frozenset({PolicyAction.DISCOVER}),
            principal_ids=frozenset({"forgeai-automation"}),
            minimum_trust_tier=TrustTier.OFFICIAL,
            maximum_risk_level=RiskLevel.LOW,
            allowed_permissions=frozenset({"network:egress:docs.example.test"}),
        )
        brain = BrainContainer.local((rule,))
        candidate = brain.lifecycle.register(
            record(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="correlation-a",
        )

        updated = brain.lifecycle.advance(
            capability_id=candidate.capability_id,
            expected_revision=candidate.revision,
            target=CapabilityStatus.VALIDATED,
            action=PolicyAction.DISCOVER,
            request=request(candidate.capability_id),
            reason="static validation passed",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="correlation-a",
        )

        self.assertEqual(CapabilityStatus.VALIDATED, updated.status)
        events = brain.events.events()
        self.assertEqual(["capability.registered.v1", "capability.transitioned.v1"], [event.event_type for event in events])
        self.assertEqual("allow", events[-1].payload["policy"]["decision"])
        self.assertEqual(1, events[-1].schema_version)

    def test_stale_transition_is_rejected(self) -> None:
        brain = BrainContainer.local()
        candidate = brain.catalog.create(record())
        brain.catalog.transition(
            candidate.capability_id,
            expected_revision=0,
            target=CapabilityStatus.VALIDATED,
            reason="validated",
        )

        with self.assertRaises(CatalogConflict):
            brain.catalog.transition(
                candidate.capability_id,
                expected_revision=0,
                target=CapabilityStatus.APPROVED,
                reason="stale approval",
            )

    def test_lifecycle_action_cannot_be_disguised_as_a_less_privileged_request(self) -> None:
        allow_discovery = DeclarativePolicyRule(
            rule_id="allow-discovery-only",
            effect=PolicyDecisionKind.ALLOW,
            actions=frozenset({PolicyAction.DISCOVER}),
        )
        brain = BrainContainer.local((allow_discovery,))
        candidate = brain.lifecycle.register(
            record(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="correlation-a",
        )

        with self.assertRaises(ValueError):
            brain.lifecycle.advance(
                capability_id=candidate.capability_id,
                expected_revision=candidate.revision,
                target=CapabilityStatus.VALIDATED,
                action=PolicyAction.INSTALL,
                request=request(candidate.capability_id, action=PolicyAction.DISCOVER),
                reason="attempt action substitution",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="correlation-a",
            )

    def test_safety_quarantine_keeps_tenant_context_without_policy_availability(self) -> None:
        brain = BrainContainer.local()
        candidate = brain.lifecycle.register(
            record(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="correlation-a",
        )

        quarantined = brain.lifecycle.advance(
            capability_id=candidate.capability_id,
            expected_revision=candidate.revision,
            target=CapabilityStatus.QUARANTINED,
            action=None,
            request=None,
            reason="malformed probe output",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            correlation_id="correlation-a",
        )

        self.assertEqual(CapabilityStatus.QUARANTINED, quarantined.status)
        event = brain.events.events()[-1]
        self.assertEqual("capability.safety_transitioned.v1", event.event_type)
        self.assertEqual("tenant-a", event.tenant_id)
        self.assertEqual("workspace-a", event.workspace_id)
