from __future__ import annotations

from datetime import timedelta
import unittest

from src.brain.domain.models import PolicyDecision, PolicyDecisionKind, utc_now
from src.brain.mcp.host import McpHostProbeError, McpHostProtocolProbe
from src.brain.mcp.installation import McpInstallationPlan, McpInstallationPlanBuilder, McpPackageArtifactVerification
from src.brain.mcp.probe import McpProbeExecutionEvidence
from src.brain.mcp.server_manifest import parse_server_manifest


SHA256_A = "sha256:" + "a" * 64


def ready_plan() -> McpInstallationPlan:
    manifest = parse_server_manifest(
        {
            "name": "io.forgeai/example",
            "version": "1.0.0",
            "packages": [
                {
                    "registryType": "pypi",
                    "identifier": "forgeai-example-mcp",
                    "version": "1.0.0",
                    "transport": {"type": "stdio"},
                }
            ],
        }
    )
    return McpInstallationPlanBuilder.for_package(
        manifest=manifest,
        package_index=0,
        verification=McpPackageArtifactVerification(
            registry_type="pypi",
            identifier="forgeai-example-mcp",
            version="1.0.0",
            evidence_id="scan:example",
            artifact_digest=SHA256_A,
            provenance_verified=True,
        ),
        capability_id="mcp.io.forgeai/example",
        candidate_id="candidate:example",
        source_metadata_hash=SHA256_A,
        policy_decision=PolicyDecision(
            kind=PolicyDecisionKind.ALLOW,
            reason_code="test-allow",
            policy_version="test-v1",
        ),
    )


def evidence() -> McpProbeExecutionEvidence:
    started = utc_now()
    return McpProbeExecutionEvidence(
        probe_id="probe:host",
        isolated_runtime_id="sandbox:host",
        credential_free=True,
        started_at=started,
        completed_at=started + timedelta(seconds=1),
    )


class FakeTransport:
    def __init__(self, responses: dict[tuple[str, str | None], dict[str, object]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.notifications: list[tuple[str, dict[str, object]]] = []
        self.protocol_versions: list[str] = []
        self.closed = False

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        self.requests.append((method, dict(params)))
        return self.responses[(method, params.get("cursor"))]

    def notify(self, method: str, params: dict[str, object]) -> None:
        self.notifications.append((method, dict(params)))

    def set_protocol_version(self, protocol_version: str) -> None:
        self.protocol_versions.append(protocol_version)

    def close(self) -> None:
        self.closed = True


def initialize(*, version: str = "2025-11-25") -> dict[str, object]:
    return {
        "protocolVersion": version,
        "serverInfo": {"name": "io.forgeai/example", "version": "1.0.0"},
        "capabilities": {
            "tools": {"listChanged": True},
            "resources": {"listChanged": False},
            "prompts": {},
        },
    }


class McpHostProtocolTests(unittest.TestCase):
    def test_host_follows_initialize_negotiation_notification_and_paginated_inventory_lifecycle(self) -> None:
        transport = FakeTransport(
            {
                ("initialize", None): initialize(),
                ("ping", None): {},
                (
                    "tools/list",
                    None,
                ): {
                    "tools": [
                        {"name": "search", "inputSchema": {"type": "object"}},
                    ],
                    "nextCursor": "page-2",
                },
                (
                    "tools/list",
                    "page-2",
                ): {
                    "tools": [
                        {
                            "name": "read",
                            "description": "Read approved content.",
                            "inputSchema": {"type": "object"},
                            "outputSchema": {"type": "object"},
                        }
                    ]
                },
                ("resources/list", None): {
                    "resources": [
                        {"uri": "forgeai://index", "name": "Index", "mimeType": "application/json"}
                    ]
                },
                ("prompts/list", None): {"prompts": [{"name": "research"}]},
            }
        )

        result = McpHostProtocolProbe(transport).probe(plan=ready_plan(), execution=evidence())

        self.assertEqual("2025-11-25", result.transcript.protocol_version)
        self.assertEqual(("search", "read"), tuple(tool.name for tool in result.transcript.tools))
        self.assertEqual(("forgeai://index",), tuple(item.uri for item in result.transcript.resources))
        self.assertEqual(("research",), tuple(item.name for item in result.transcript.prompts))
        self.assertTrue(result.tools_list_changed)
        self.assertFalse(result.resources_list_changed)
        self.assertFalse(result.prompts_list_changed)
        self.assertTrue(result.ping_succeeded)
        self.assertEqual(["2025-11-25"], transport.protocol_versions)
        self.assertEqual([("notifications/initialized", {})], transport.notifications)
        self.assertEqual(
            [
                ("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "ForgeAI", "version": "0.1.0"}}),
                ("ping", {}),
                ("tools/list", {}),
                ("tools/list", {"cursor": "page-2"}),
                ("resources/list", {}),
                ("prompts/list", {}),
            ],
            transport.requests,
        )
        self.assertTrue(transport.closed)

    def test_unsupported_negotiated_version_is_rejected_before_initialized_notification(self) -> None:
        transport = FakeTransport({("initialize", None): initialize(version="2024-11-05")})

        with self.assertRaises(McpHostProbeError):
            McpHostProtocolProbe(transport).probe(plan=ready_plan(), execution=evidence())

        self.assertEqual([], transport.protocol_versions)
        self.assertEqual([], transport.notifications)
        self.assertTrue(transport.closed)

    def test_repeated_pagination_cursor_is_rejected_and_transport_is_closed(self) -> None:
        transport = FakeTransport(
            {
                ("initialize", None): initialize(),
                ("ping", None): {},
                ("tools/list", None): {"tools": [], "nextCursor": "repeat"},
                ("tools/list", "repeat"): {"tools": [], "nextCursor": "repeat"},
            }
        )

        with self.assertRaises(McpHostProbeError):
            McpHostProtocolProbe(transport).probe(plan=ready_plan(), execution=evidence())

        self.assertTrue(transport.closed)
        self.assertEqual([], transport.notifications[1:])
