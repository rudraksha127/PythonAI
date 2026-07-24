"""Non-executing filesystem discovery for ForgeAI plugin manifests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..contracts.plugin_manifest import ManifestValidationError, parse_plugin_manifest_document
from ..domain.models import PluginManifest, freeze_mapping


@dataclass(frozen=True, slots=True)
class DiscoveredPluginManifest:
    """A statically validated manifest plus immutable provenance evidence."""

    manifest: PluginManifest
    source_path: str
    raw_metadata_hash: str
    raw_document: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_document", freeze_mapping(self.raw_document))


@dataclass(frozen=True, slots=True)
class ManifestDiscoveryError:
    """A per-file validation failure that must not stop all discovery."""

    source_path: str
    message: str


@dataclass(frozen=True, slots=True)
class ManifestDiscoveryResult:
    """All static discovery observations from a directory scan."""

    manifests: tuple[DiscoveredPluginManifest, ...]
    errors: tuple[ManifestDiscoveryError, ...]


class FilesystemPluginManifestSource:
    """Discover `plugin.json` files without following symlinks or executing code."""

    def __init__(self, root: str | Path, *, max_manifest_bytes: int = 1_000_000) -> None:
        self._root = Path(root)
        if max_manifest_bytes < 1:
            raise ValueError("max_manifest_bytes must be positive")
        self._max_manifest_bytes = max_manifest_bytes

    def discover(self) -> ManifestDiscoveryResult:
        if not self._root.exists():
            return ManifestDiscoveryResult(manifests=(), errors=())
        if not self._root.is_dir():
            raise ValueError(f"plugin manifest root is not a directory: {self._root}")

        root = self._root.resolve()
        manifests: list[DiscoveredPluginManifest] = []
        errors: list[ManifestDiscoveryError] = []
        observed_releases: set[tuple[str, str]] = set()

        for path in sorted(self._manifest_paths(root)):
            relative_path = str(path.relative_to(root))
            try:
                if path.is_symlink():
                    raise ManifestValidationError("symbolic-link manifests are not accepted")
                if path.stat().st_size > self._max_manifest_bytes:
                    raise ManifestValidationError(
                        f"manifest exceeds {self._max_manifest_bytes} byte safety limit"
                    )
                raw_bytes = path.read_bytes()
                document = json.loads(raw_bytes.decode("utf-8"))
                if not isinstance(document, Mapping):
                    raise ManifestValidationError("manifest root must be a JSON object")
                manifest = parse_plugin_manifest_document(document)
                release_key = (manifest.plugin_id, manifest.version)
                if release_key in observed_releases:
                    raise ManifestValidationError(
                        f"duplicate plugin release {manifest.plugin_id!r}@{manifest.version!r}"
                    )
                observed_releases.add(release_key)
                manifests.append(
                    DiscoveredPluginManifest(
                        manifest=manifest,
                        source_path=relative_path,
                        raw_metadata_hash=f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}",
                        raw_document=document,
                    )
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ManifestValidationError) as error:
                errors.append(ManifestDiscoveryError(source_path=relative_path, message=str(error)))

        return ManifestDiscoveryResult(manifests=tuple(manifests), errors=tuple(errors))

    @staticmethod
    def _manifest_paths(root: Path) -> tuple[Path, ...]:
        paths: list[Path] = []
        for path in root.rglob("plugin.json"):
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            paths.append(path)
        return tuple(paths)
