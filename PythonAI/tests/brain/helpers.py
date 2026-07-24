"""Dependency-free fixtures for the ForgeAI Brain unit tests."""

from __future__ import annotations

from src.brain.domain.models import (
    ArtifactReference,
    CapabilityCandidate,
    CapabilityDescriptor,
    CapabilityRecord,
    PluginManifest,
    PluginRuntime,
    RiskLevel,
    TrustTier,
)


def record(
    capability_id: str = "io.forgeai.search.docs",
    *,
    kind: str = "knowledge-search",
    risk_level: RiskLevel = RiskLevel.LOW,
    trust_tier: TrustTier = TrustTier.OFFICIAL,
    tags: frozenset[str] = frozenset({"docs", "search"}),
) -> CapabilityRecord:
    descriptor = CapabilityDescriptor(
        capability_id=capability_id,
        version="1.0.0",
        name="Documentation search",
        description="Searches approved documentation sources.",
        kind=kind,
        risk_level=risk_level,
        tags=tags,
        required_permissions=frozenset({"network:egress:docs.example.test"}),
    )
    candidate = CapabilityCandidate(
        candidate_id=f"candidate:{capability_id}",
        capability_id=capability_id,
        source_name="official-test-registry",
        source_url="https://registry.example.test/candidate",
        trust_tier=trust_tier,
        artifact=ArtifactReference(
            kind="python-package",
            locator="example-capability",
            version="1.0.0",
            digest="sha256:test",
        ),
        raw_metadata_hash="sha256:metadata",
    )
    manifest = PluginManifest(
        plugin_id=f"plugin:{capability_id}",
        version="1.0.0",
        publisher="forgeai-test",
        kind="capability-provider",
        runtime=PluginRuntime.PYTHON_WORKER,
        entrypoint="example.plugin:Plugin",
        provided_capability_ids=(capability_id,),
        requested_permissions=descriptor.required_permissions,
    )
    return CapabilityRecord(descriptor=descriptor, candidate=candidate, manifest=manifest)
