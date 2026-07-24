from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.brain.adapters.in_memory import DeclarativePolicyRule, DefaultDenyPolicyEngine
from src.brain.adapters.sqlite_store import SqliteCapabilityStore
from src.brain.application.ports import CatalogConflict
from src.brain.application.services import CapabilityLifecycleService
from src.brain.domain.events import new_event
from src.brain.domain.models import CapabilityStatus, PolicyAction, PolicyDecisionKind, PolicyRequest, RiskLevel, TrustTier
from src.brain.runtime.container import BrainContainer

from .helpers import record


def discovery_request(capability_id: str) -> PolicyRequest:
    return PolicyRequest(
        action=PolicyAction.DISCOVER,
        principal_id="forgeai-system",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        capability_id=capability_id,
        risk_level=RiskLevel.LOW,
        trust_tier=TrustTier.OFFICIAL,
        sandboxed=False,
    )


class SqliteCapabilityStoreTests(unittest.TestCase):
    def test_atomic_register_and_transition_survive_reopen_with_pending_outbox_events(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "forgeai.sqlite3"
            store = SqliteCapabilityStore(database)
            policy = DefaultDenyPolicyEngine(
                [
                    DeclarativePolicyRule(
                        rule_id="allow-discovery",
                        effect=PolicyDecisionKind.ALLOW,
                        actions=frozenset({PolicyAction.DISCOVER}),
                    )
                ]
            )
            lifecycle = CapabilityLifecycleService(store, policy, store, atomic_lifecycle=store)
            created = lifecycle.register(
                record(),
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="corr-register",
            )
            updated = lifecycle.advance(
                capability_id=created.capability_id,
                expected_revision=created.revision,
                target=CapabilityStatus.VALIDATED,
                action=PolicyAction.DISCOVER,
                request=discovery_request(created.capability_id),
                reason="metadata validated",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="corr-validate",
            )

            self.assertEqual(CapabilityStatus.VALIDATED, updated.status)
            self.assertEqual(1, updated.revision)
            store.close()

            reopened = SqliteCapabilityStore(database)
            try:
                persisted = reopened.get(created.capability_id)
                self.assertIsNotNone(persisted)
                self.assertEqual(CapabilityStatus.VALIDATED, persisted.status)  # type: ignore[union-attr]
                self.assertEqual(1, persisted.revision)  # type: ignore[union-attr]
                self.assertEqual(
                    ["capability.registered.v1", "capability.transitioned.v1"],
                    [event.event_type for event in reopened.pending_events()],
                )
            finally:
                reopened.close()

    def test_failed_event_factory_rolls_back_its_transition_and_outbox_write_together(self) -> None:
        store = SqliteCapabilityStore(":memory:")
        created = store.create_with_event(
            record(),
            new_event(
                event_type="capability.registered.v1",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                subject_id="io.forgeai.search.docs",
                correlation_id="corr-register",
            ),
        )

        def broken_event_factory(_: object) -> object:
            raise RuntimeError("simulated outbox serialization failure")

        with self.assertRaises(RuntimeError):
            store.transition_with_event(
                created.capability_id,
                expected_revision=0,
                target=CapabilityStatus.VALIDATED,
                reason="validated",
                event_factory=broken_event_factory,  # type: ignore[arg-type]
            )

        current = store.get(created.capability_id)
        self.assertIsNotNone(current)
        self.assertEqual(CapabilityStatus.CANDIDATE, current.status)  # type: ignore[union-attr]
        self.assertEqual(0, current.revision)  # type: ignore[union-attr]
        self.assertEqual(1, len(store.pending_events()))
        store.close()

    def test_outbox_is_idempotent_and_can_mark_delivery_without_deleting_audit_history(self) -> None:
        store = SqliteCapabilityStore(":memory:")
        event = new_event(
            event_type="mcp.install_plan.created.v1",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            subject_id="mcp.example",
            correlation_id="corr-outbox",
            payload={"plan_id": "plan-1"},
        )
        store.publish(event)
        store.publish(event)
        self.assertEqual([event.event_id], [item.event_id for item in store.pending_events()])

        store.mark_published(event.event_id)
        self.assertEqual((), tuple(store.pending_events()))
        store.mark_published(event.event_id)
        self.assertEqual((), tuple(store.pending_events()))
        store.close()

    def test_optimistic_concurrency_is_preserved_by_the_durable_store(self) -> None:
        store = SqliteCapabilityStore(":memory:")
        created = store.create(record())
        store.transition(
            created.capability_id,
            expected_revision=0,
            target=CapabilityStatus.VALIDATED,
            reason="validated",
        )

        with self.assertRaises(CatalogConflict):
            store.transition(
                created.capability_id,
                expected_revision=0,
                target=CapabilityStatus.APPROVED,
                reason="stale approval",
            )
        store.close()

    def test_composition_root_can_select_the_durable_adapter_without_changing_use_cases(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            brain = BrainContainer.sqlite(Path(temporary_directory) / "brain.sqlite3")
            created = brain.lifecycle.register(
                record(),
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                correlation_id="corr-container",
            )
            self.assertEqual(created.capability_id, brain.catalog.get(created.capability_id).capability_id)  # type: ignore[union-attr]
            self.assertEqual("capability.registered.v1", brain.events.pending_events()[0].event_type)  # type: ignore[attr-defined]
            brain.events.close()  # type: ignore[attr-defined]
