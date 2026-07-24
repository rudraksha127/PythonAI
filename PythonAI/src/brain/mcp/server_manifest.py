"""Static parser for MCP Registry-compatible ``server.json`` metadata.

Registry metadata is untrusted discovery input. This module deliberately does
not invoke package managers, run commands, expand environment variables, open
network sockets, or resolve OAuth. It turns a document into a normalized,
auditable plan for later policy and installation stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlparse

from ..domain.models import freeze_mapping


class ServerManifestValidationError(ValueError):
    """Raised when server metadata does not satisfy ForgeAI's static contract."""


class McpTransportType(str, Enum):
    """Transport names accepted from an MCP server manifest."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"
    WEBSOCKET = "websocket"

    @property
    def is_core_transport(self) -> bool:
        return self in {McpTransportType.STDIO, McpTransportType.STREAMABLE_HTTP}


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServerManifestValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ServerManifestValidationError(f"{field_name} must be an object")
    return value


def _list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ServerManifestValidationError(f"{field_name} must be an array")
    return value


def _transport(value: Any, field_name: str) -> McpTransportType:
    transport = _mapping(value, field_name)
    try:
        return McpTransportType(_text(transport.get("type"), f"{field_name}.type"))
    except ValueError as error:
        names = ", ".join(item.value for item in McpTransportType)
        raise ServerManifestValidationError(f"{field_name}.type must be one of: {names}") from error


@dataclass(frozen=True, slots=True)
class McpEnvironmentVariable:
    """A declaration of a runtime variable, never its resolved value."""

    name: str
    is_required: bool = False
    is_secret: bool = False
    description: str | None = None
    default: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, "environmentVariable.name")
        if self.description is not None:
            _text(self.description, "environmentVariable.description")
        if self.default is not None and not isinstance(self.default, str):
            raise ServerManifestValidationError("environmentVariable.default must be a string")


@dataclass(frozen=True, slots=True)
class McpPackageSpec:
    """A package distribution option advertised by an MCP server manifest."""

    registry_type: str
    identifier: str
    transport: McpTransportType
    version: str | None = None
    registry_base_url: str | None = None
    runtime_hint: str | None = None
    environment_variables: tuple[McpEnvironmentVariable, ...] = ()
    package_arguments: tuple[Mapping[str, Any], ...] = ()
    runtime_arguments: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.registry_type, "package.registry_type")
        _text(self.identifier, "package.identifier")
        if self.version is not None:
            _text(self.version, "package.version")
        if self.registry_base_url is not None:
            _text(self.registry_base_url, "package.registry_base_url")
        if self.runtime_hint is not None:
            _text(self.runtime_hint, "package.runtime_hint")
        object.__setattr__(self, "package_arguments", tuple(freeze_mapping(item) for item in self.package_arguments))
        object.__setattr__(self, "runtime_arguments", tuple(freeze_mapping(item) for item in self.runtime_arguments))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class McpRemoteSpec:
    """A remote MCP endpoint advertised by a server manifest."""

    transport: McpTransportType
    url: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.url, "remote.url")
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ServerManifestValidationError("remote.url must be an absolute HTTP(S) URL")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class McpStaticRiskFinding:
    """A static finding that must be evaluated by policy before activation."""

    code: str
    subject: str
    detail: str


@dataclass(frozen=True, slots=True)
class McpServerManifest:
    """Normalized server metadata with package and remote install alternatives."""

    server_name: str
    version: str | None
    description: str | None
    packages: tuple[McpPackageSpec, ...]
    remotes: tuple[McpRemoteSpec, ...]
    source_url: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.server_name, "server.name")
        if self.version is not None:
            _text(self.version, "server.version")
        if self.description is not None:
            _text(self.description, "server.description")
        if not self.packages and not self.remotes:
            raise ServerManifestValidationError("server must advertise at least one package or remote")
        if self.source_url is not None:
            _text(self.source_url, "server.source_url")
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    def static_risk_findings(self) -> tuple[McpStaticRiskFinding, ...]:
        """Return evidence; this method never makes an allow/deny decision."""

        findings: list[McpStaticRiskFinding] = []
        for package in self.packages:
            subject = f"{package.registry_type}:{package.identifier}"
            if package.version is None:
                findings.append(
                    McpStaticRiskFinding(
                        code="package-version-unpinned",
                        subject=subject,
                        detail="Artifact resolver must select an exact package version before installation.",
                    )
                )
            findings.append(
                McpStaticRiskFinding(
                    code="artifact-digest-unverified",
                    subject=subject,
                    detail="Registry metadata does not prove the installed artifact digest.",
                )
            )
            if package.runtime_arguments:
                findings.append(
                    McpStaticRiskFinding(
                        code="runtime-arguments-requested",
                        subject=subject,
                        detail="Runtime arguments require policy review before process or container launch.",
                    )
                )
            for variable in package.environment_variables:
                if variable.is_secret:
                    findings.append(
                        McpStaticRiskFinding(
                            code="secret-required",
                            subject=subject,
                            detail=f"Runtime variable {variable.name!r} is marked secret.",
                        )
                    )
        for remote in self.remotes:
            parsed = urlparse(remote.url)
            if parsed.scheme != "https":
                findings.append(
                    McpStaticRiskFinding(
                        code="remote-not-https",
                        subject=remote.url,
                        detail="Remote endpoints require an explicit local-development or policy exception.",
                    )
                )
            if parsed.username or parsed.password:
                findings.append(
                    McpStaticRiskFinding(
                        code="remote-url-contains-userinfo",
                        subject=remote.url,
                        detail="Credentials must not be embedded in a remote endpoint URL.",
                    )
                )
            if not remote.transport.is_core_transport:
                findings.append(
                    McpStaticRiskFinding(
                        code="legacy-or-optional-transport",
                        subject=remote.url,
                        detail=f"{remote.transport.value} is a compatibility transport, not a core transport.",
                    )
                )
        return tuple(findings)


def _environment_variables(value: Any, field_name: str) -> tuple[McpEnvironmentVariable, ...]:
    if value is None:
        return ()
    result: list[McpEnvironmentVariable] = []
    for index, item in enumerate(_list(value, field_name)):
        raw = _mapping(item, f"{field_name}[{index}]")
        name = _text(raw.get("name"), f"{field_name}[{index}].name")
        is_required = raw.get("isRequired", False)
        is_secret = raw.get("isSecret", False)
        if not isinstance(is_required, bool) or not isinstance(is_secret, bool):
            raise ServerManifestValidationError(
                f"{field_name}[{index}].isRequired and isSecret must be booleans"
            )
        description = raw.get("description")
        default = raw.get("default")
        result.append(
            McpEnvironmentVariable(
                name=name,
                is_required=is_required,
                is_secret=is_secret,
                description=description,
                default=default,
            )
        )
    return tuple(result)


def _argument_list(value: Any, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    return tuple(
        _mapping(argument, f"{field_name}[{index}]")
        for index, argument in enumerate(_list(value, field_name))
    )


def _packages(value: Any, server_version: str | None) -> tuple[McpPackageSpec, ...]:
    if value is None:
        return ()
    packages: list[McpPackageSpec] = []
    for index, item in enumerate(_list(value, "packages")):
        raw = _mapping(item, f"packages[{index}]")
        package_version = raw.get("version", server_version)
        if package_version is not None:
            package_version = _text(package_version, f"packages[{index}].version")
        packages.append(
            McpPackageSpec(
                registry_type=_text(raw.get("registryType"), f"packages[{index}].registryType"),
                identifier=_text(raw.get("identifier"), f"packages[{index}].identifier"),
                version=package_version,
                registry_base_url=(
                    _text(raw["registryBaseUrl"], f"packages[{index}].registryBaseUrl")
                    if raw.get("registryBaseUrl") is not None
                    else None
                ),
                runtime_hint=(
                    _text(raw["runtimeHint"], f"packages[{index}].runtimeHint")
                    if raw.get("runtimeHint") is not None
                    else None
                ),
                transport=_transport(raw.get("transport"), f"packages[{index}].transport"),
                environment_variables=_environment_variables(
                    raw.get("environmentVariables"), f"packages[{index}].environmentVariables"
                ),
                package_arguments=_argument_list(raw.get("packageArguments"), f"packages[{index}].packageArguments"),
                runtime_arguments=_argument_list(raw.get("runtimeArguments"), f"packages[{index}].runtimeArguments"),
                metadata=raw,
            )
        )
    return tuple(packages)


def _remotes(value: Any) -> tuple[McpRemoteSpec, ...]:
    if value is None:
        return ()
    remotes: list[McpRemoteSpec] = []
    for index, item in enumerate(_list(value, "remotes")):
        raw = _mapping(item, f"remotes[{index}]")
        remotes.append(
            McpRemoteSpec(
                transport=_transport(raw, f"remotes[{index}]"),
                url=_text(raw.get("url"), f"remotes[{index}].url"),
                metadata=raw,
            )
        )
    return tuple(remotes)


def parse_server_manifest(
    document: Mapping[str, Any],
    *,
    source_url: str | None = None,
) -> McpServerManifest:
    """Normalize a registry ``server.json`` document without executing it."""

    root = _mapping(document, "server")
    version = root.get("version")
    if version is not None:
        version = _text(version, "server.version")
    description = root.get("description")
    if description is not None:
        description = _text(description, "server.description")
    return McpServerManifest(
        server_name=_text(root.get("name"), "server.name"),
        version=version,
        description=description,
        packages=_packages(root.get("packages"), version),
        remotes=_remotes(root.get("remotes")),
        source_url=source_url,
        metadata=root,
    )
