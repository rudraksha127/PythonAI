from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.brain.adapters.plugin_manifest_source import FilesystemPluginManifestSource
from src.brain.contracts.plugin_manifest import ManifestValidationError, parse_plugin_manifest_document
from src.brain.domain.models import PluginRuntime


def document(plugin_id: str = "io.forgeai.example", version: str = "1.0.0") -> dict[str, object]:
    return {
        "apiVersion": "forgeai.dev/plugin/v1",
        "kind": "capability-provider",
        "metadata": {
            "id": plugin_id,
            "version": version,
            "publisher": "forgeai-test",
        },
        "spec": {
            "provides": ["io.forgeai.example.search"],
            "runtime": {"type": "python-worker"},
            "entrypoint": "does.not.need.to.exist:Plugin",
            "permissions": {
                "network": {"egress": ["registry.example.test"]},
                "filesystem": {"read": ["/workspace"], "write": []},
                "shell": False,
            },
            "compatibility": {"kernel": ">=1.0,<2.0"},
        },
    }


class PluginManifestDiscoveryTests(unittest.TestCase):
    def test_parser_normalizes_structured_permission_scopes_without_importing_entrypoint(self) -> None:
        manifest = parse_plugin_manifest_document(document())

        self.assertEqual(PluginRuntime.PYTHON_WORKER, manifest.runtime)
        self.assertEqual(
            frozenset(
                {
                    "network:egress:registry.example.test",
                    "filesystem:read:/workspace",
                }
            ),
            manifest.requested_permissions,
        )
        self.assertEqual(("io.forgeai.example.search",), manifest.provided_capability_ids)

    def test_parser_rejects_an_unknown_runtime_before_any_execution(self) -> None:
        invalid = document()
        invalid["spec"]["runtime"] = {"type": "totally-unknown"}  # type: ignore[index]

        with self.assertRaises(ManifestValidationError):
            parse_plugin_manifest_document(invalid)

    def test_filesystem_discovery_collects_valid_manifests_and_isolates_bad_files(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid_path = root / "a-valid" / "plugin.json"
            valid_path.parent.mkdir()
            valid_path.write_text(json.dumps(document()), encoding="utf-8")

            malformed_path = root / "bad-json" / "plugin.json"
            malformed_path.parent.mkdir()
            malformed_path.write_text("{not json", encoding="utf-8")

            duplicate_path = root / "duplicate" / "plugin.json"
            duplicate_path.parent.mkdir()
            duplicate_path.write_text(json.dumps(document()), encoding="utf-8")

            result = FilesystemPluginManifestSource(root).discover()

        self.assertEqual(1, len(result.manifests))
        self.assertEqual("a-valid\\plugin.json", result.manifests[0].source_path)
        self.assertTrue(result.manifests[0].raw_metadata_hash.startswith("sha256:"))
        self.assertEqual(2, len(result.errors))
        self.assertTrue(any("duplicate plugin release" in error.message for error in result.errors))
        self.assertTrue(any("Expecting property name" in error.message for error in result.errors))
