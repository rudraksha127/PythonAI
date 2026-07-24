from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.brain.domain.models import (
    CapabilityRequirement,
    CapabilityStatus,
    RiskLevel,
    TrustTier,
)
from src.brain.runtime.container import BrainContainer

from .helpers import record


def make_active(brain: BrainContainer, capability_id: str, *, trust_tier: TrustTier, risk: RiskLevel):
    current = brain.catalog.create(record(capability_id, trust_tier=trust_tier, risk_level=risk))
    for status in (
        CapabilityStatus.VALIDATED,
        CapabilityStatus.APPROVED,
        CapabilityStatus.INSTALLING,
        CapabilityStatus.INSTALLED,
        CapabilityStatus.PROBING,
        CapabilityStatus.ACTIVE,
    ):
        current = brain.catalog.transition(
            capability_id,
            expected_revision=current.revision,
            target=status,
            reason=f"fixture transition to {status.value}",
        )
    return current


class ResolverAndContractsTests(unittest.TestCase):
    def test_resolver_prefers_higher_trust_then_lower_risk(self) -> None:
        brain = BrainContainer.local()
        make_active(
            brain,
            "io.forgeai.search.community",
            trust_tier=TrustTier.COMMUNITY,
            risk=RiskLevel.LOW,
        )
        expected = make_active(
            brain,
            "io.forgeai.search.official",
            trust_tier=TrustTier.OFFICIAL,
            risk=RiskLevel.MEDIUM,
        )
        requirement = CapabilityRequirement(
            requirement_id="find-documentation",
            kind="knowledge-search",
            required_tags=frozenset({"docs"}),
            minimum_trust_tier=TrustTier.COMMUNITY,
        )

        resolved = brain.resolver.resolve(requirement)

        self.assertIsNotNone(resolved)
        self.assertEqual(expected.capability_id, resolved.record.capability_id)

    def test_resolver_never_returns_a_degraded_or_untrusted_record(self) -> None:
        brain = BrainContainer.local()
        current = make_active(
            brain,
            "io.forgeai.search.degraded",
            trust_tier=TrustTier.COMMUNITY,
            risk=RiskLevel.LOW,
        )
        brain.catalog.transition(
            current.capability_id,
            expected_revision=current.revision,
            target=CapabilityStatus.DEGRADED,
            reason="health check failed",
        )
        requirement = CapabilityRequirement(
            requirement_id="find-documentation",
            kind="knowledge-search",
            required_tags=frozenset({"docs"}),
            minimum_trust_tier=TrustTier.COMMUNITY,
        )

        self.assertIsNone(brain.resolver.resolve(requirement))

    def test_plugin_manifest_schema_is_valid_json_schema_document(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "brain"
            / "contracts"
            / "plugin_manifest.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual("forgeai.dev/plugin/v1", schema["properties"]["apiVersion"]["const"])
        self.assertIn("provides", schema["properties"]["spec"]["properties"])
