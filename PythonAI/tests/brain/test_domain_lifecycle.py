from __future__ import annotations

import unittest

from src.brain.domain.lifecycle import CapabilityLifecycleError, transition
from src.brain.domain.models import CapabilityStatus

from .helpers import record


class CapabilityLifecycleTests(unittest.TestCase):
    def test_only_declared_transitions_are_allowed(self) -> None:
        current = record()
        for target in (
            CapabilityStatus.VALIDATED,
            CapabilityStatus.APPROVED,
            CapabilityStatus.INSTALLING,
            CapabilityStatus.INSTALLED,
            CapabilityStatus.PROBING,
            CapabilityStatus.ACTIVE,
        ):
            current = transition(current, target, reason=f"advance to {target.value}")

        self.assertEqual(CapabilityStatus.ACTIVE, current.status)
        self.assertEqual(6, current.revision)
        self.assertEqual("advance to active", current.last_transition_reason)

    def test_direct_candidate_activation_is_rejected(self) -> None:
        with self.assertRaises(CapabilityLifecycleError):
            transition(record(), CapabilityStatus.ACTIVE, reason="skip validation")

    def test_transition_requires_an_auditable_reason(self) -> None:
        with self.assertRaises(CapabilityLifecycleError):
            transition(record(), CapabilityStatus.VALIDATED, reason=" ")
