from __future__ import annotations

import unittest

from src.brain.mcp.server_manifest import (
    McpTransportType,
    ServerManifestValidationError,
    parse_server_manifest,
)


def package_server() -> dict[str, object]:
    return {
        "name": "io.forgeai/example-search",
        "version": "1.2.3",
        "description": "Example search server",
        "packages": [
            {
                "registryType": "pypi",
                "registryBaseUrl": "https://pypi.org",
                "identifier": "example-search-mcp",
                "runtimeHint": "uvx",
                "transport": {"type": "stdio"},
                "environmentVariables": [
                    {"name": "SEARCH_API_KEY", "isRequired": True, "isSecret": True}
                ],
                "runtimeArguments": [{"type": "named", "name": "--read-only"}],
            }
        ],
    }


class McpServerManifestTests(unittest.TestCase):
    def test_package_metadata_is_normalized_but_not_executed(self) -> None:
        manifest = parse_server_manifest(
            package_server(), source_url="https://registry.example.test/servers/example"
        )

        self.assertEqual("io.forgeai/example-search", manifest.server_name)
        package = manifest.packages[0]
        self.assertEqual(McpTransportType.STDIO, package.transport)
        self.assertEqual("1.2.3", package.version)
        self.assertEqual("SEARCH_API_KEY", package.environment_variables[0].name)
        findings = {finding.code for finding in manifest.static_risk_findings()}
        self.assertIn("artifact-digest-unverified", findings)
        self.assertIn("secret-required", findings)
        self.assertIn("runtime-arguments-requested", findings)

    def test_remote_manifest_surfaces_risk_signals_without_connecting(self) -> None:
        manifest = parse_server_manifest(
            {
                "name": "io.forgeai/remote",
                "remotes": [
                    {
                        "type": "sse",
                        "url": "http://user:password@localhost:8888/sse",
                    }
                ],
            }
        )

        findings = {finding.code for finding in manifest.static_risk_findings()}
        self.assertIn("remote-not-https", findings)
        self.assertIn("remote-url-contains-userinfo", findings)
        self.assertIn("legacy-or-optional-transport", findings)

    def test_unknown_transport_is_rejected_during_static_validation(self) -> None:
        invalid = package_server()
        invalid["packages"][0]["transport"] = {"type": "arbitrary-shell"}  # type: ignore[index]

        with self.assertRaises(ServerManifestValidationError):
            parse_server_manifest(invalid)

    def test_server_without_any_install_or_remote_option_is_rejected(self) -> None:
        with self.assertRaises(ServerManifestValidationError):
            parse_server_manifest({"name": "io.forgeai/empty"})
