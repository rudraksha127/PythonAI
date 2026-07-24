"""Static parsing for the ForgeAI plugin-manifest interchange document.

The parser intentionally validates metadata only. It never imports an entry
point, starts a process, resolves a package, or expands environment variables.
Those operations belong to separately policy-controlled lifecycle stages.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping

from ..domain.models import PluginManifest, PluginRuntime


class ManifestValidationError(ValueError):
    """Raised when a manifest document fails static contract validation."""


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestValidationError(f"{field_name} must be an object")
    return value


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _text_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestValidationError(f"{field_name} must be a non-empty array")
    values = tuple(_text(item, f"{field_name}[{index}]") for index, item in enumerate(value))
    if len(set(values)) != len(values):
        raise ManifestValidationError(f"{field_name} must contain unique values")
    return values


def _permission_identifiers(value: Mapping[str, Any]) -> frozenset[str]:
    """Flatten structured scopes into stable policy identifiers.

    Examples:
      {"network": {"egress": ["registry.example"]}}
        -> {"network:egress:registry.example"}
      {"shell": true} -> {"shell"}

    Empty collections are declarations without a requested scope and therefore
    do not grant or request a permission.
    """

    permissions: set[str] = set()

    def visit(item: Any, path: tuple[str, ...]) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str) or not key.strip():
                    raise ManifestValidationError("permission keys must be non-empty strings")
                visit(nested, (*path, key.strip()))
            return
        if isinstance(item, list | tuple | set | frozenset):
            for nested in item:
                visit(nested, path)
            return
        if item is True:
            if not path:
                raise ManifestValidationError("a boolean permission requires a scope name")
            permissions.add(":".join(path))
            return
        if item is False or item is None:
            return
        if isinstance(item, str):
            if not item.strip():
                raise ManifestValidationError("permission scope values may not be blank")
            permissions.add(":".join((*path, item.strip())))
            return
        if isinstance(item, int | float):
            permissions.add(":".join((*path, str(item))))
            return
        raise ManifestValidationError(
            f"unsupported permission value at {':'.join(path) or '<root>'}: {type(item).__name__}"
        )

    visit(value, ())
    return frozenset(permissions)


def parse_plugin_manifest_document(document: Mapping[str, Any]) -> PluginManifest:
    """Parse a JSON/YAML-compatible manifest into the immutable domain contract."""

    root = _mapping(document, "manifest")
    if root.get("apiVersion") != "forgeai.dev/plugin/v1":
        raise ManifestValidationError("apiVersion must equal 'forgeai.dev/plugin/v1'")
    kind = _text(root.get("kind"), "kind")
    metadata = _mapping(root.get("metadata"), "metadata")
    spec = _mapping(root.get("spec"), "spec")
    runtime = _mapping(spec.get("runtime"), "spec.runtime")
    compatibility_value = spec.get("compatibility", {})
    compatibility = _mapping(compatibility_value, "spec.compatibility")
    permissions = _mapping(spec.get("permissions", {}), "spec.permissions")

    try:
        runtime_type = PluginRuntime(_text(runtime.get("type"), "spec.runtime.type"))
    except ValueError as error:
        allowed = ", ".join(value.value for value in PluginRuntime)
        raise ManifestValidationError(f"spec.runtime.type must be one of: {allowed}") from error

    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in compatibility.items()):
        raise ManifestValidationError("spec.compatibility must map strings to strings")

    return PluginManifest(
        plugin_id=_text(metadata.get("id"), "metadata.id"),
        version=_text(metadata.get("version"), "metadata.version"),
        publisher=_text(metadata.get("publisher"), "metadata.publisher"),
        kind=kind,
        runtime=runtime_type,
        entrypoint=_text(spec.get("entrypoint"), "spec.entrypoint"),
        provided_capability_ids=_text_list(spec.get("provides"), "spec.provides"),
        requested_permissions=_permission_identifiers(permissions),
        api_version="forgeai.dev/plugin/v1",
        compatibility={str(key): str(value) for key, value in compatibility.items()},
        metadata={"manifest_kind": kind},
    )
