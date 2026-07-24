from __future__ import annotations

import unittest

from src.brain.adapters.mcp_registry import OfficialMcpRegistrySource


def response() -> dict[str, object]:
    return {
        "metadata": {"count": 2, "next_cursor": "next-page", "total": 12},
        "servers": [
            {
                "server": {
                    "name": "io.forgeai/example",
                    "version": "1.0.0",
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "@forgeai/example",
                            "version": "1.0.0",
                            "transport": {"type": "stdio"},
                        }
                    ],
                },
                "_meta": {
                    "io.modelcontextprotocol.registry/official": {
                        "id": "registry-id-1",
                        "status": "active",
                        "is_latest": True,
                        "published_at": "2026-07-23T00:00:00Z",
                    }
                },
            },
            {"server": {"name": "broken-without-options"}},
        ],
    }


class OfficialMcpRegistrySourceTests(unittest.TestCase):
    def test_page_fetch_normalizes_active_entries_and_isolates_invalid_ones(self) -> None:
        observed_urls: list[str] = []

        def fetch(url: str, timeout: float, max_bytes: int):
            observed_urls.append(url)
            self.assertEqual(10.0, timeout)
            self.assertGreater(max_bytes, 0)
            return response()

        source = OfficialMcpRegistrySource(fetch_json=fetch)
        page = source.list_servers(search="example", limit=10)

        self.assertEqual(1, len(page.observations))
        observation = page.observations[0]
        self.assertEqual("io.forgeai/example", observation.manifest.server_name)
        self.assertEqual("registry-id-1", observation.registry_id)
        self.assertTrue(observation.eligible_for_activation)
        self.assertTrue(observation.raw_metadata_hash.startswith("sha256:"))
        self.assertEqual("next-page", page.next_cursor)
        self.assertEqual(12, page.total)
        self.assertEqual(1, len(page.errors))
        self.assertIn("search=example", observed_urls[0])
        self.assertIn("limit=10", observed_urls[0])

    def test_deprecated_entry_is_discovered_but_not_eligible_for_auto_activation(self) -> None:
        def fetch(url: str, timeout: float, max_bytes: int):
            data = response()
            data["servers"][0]["_meta"]["io.modelcontextprotocol.registry/official"]["status"] = "deprecated"  # type: ignore[index]
            return data

        observation = OfficialMcpRegistrySource(fetch_json=fetch).list_servers().observations[0]

        self.assertFalse(observation.eligible_for_activation)

    def test_custom_registry_requires_an_explicit_https_host_allowlist(self) -> None:
        with self.assertRaises(ValueError):
            OfficialMcpRegistrySource(base_url="http://registry.example.test/v0.1")
        with self.assertRaises(ValueError):
            OfficialMcpRegistrySource(base_url="https://registry.example.test/v0.1")

        source = OfficialMcpRegistrySource(
            base_url="https://registry.example.test/v0.1",
            allowed_hosts=frozenset({"registry.example.test"}),
            fetch_json=lambda url, timeout, max_bytes: {"servers": []},
        )
        self.assertEqual((), source.list_servers().observations)
