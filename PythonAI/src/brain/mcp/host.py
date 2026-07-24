"""Protocol-correct, transport-neutral MCP host probe client.

The injected transport is responsible for stdio or Streamable HTTP mechanics
inside an already-provisioned sandbox. This host client owns MCP lifecycle:
initialize, version/capability negotiation, initialized notification, bounded
pagination, metadata normalization, and shutdown. It never calls a tool.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol, TypeVar

from ..domain.models import freeze_mapping
from .installation import McpInstallationPlan
from .probe import (
    McpProbeExecutionEvidence,
    McpProbeTranscript,
    McpPromptDescriptor,
    McpResourceDescriptor,
    McpToolDescriptor,
)


_PROTOCOL_VERSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_Item = TypeVar("_Item")


class McpHostProbeError(RuntimeError):
    """Raised when MCP lifecycle, negotiation, or metadata rules are violated."""


class McpJsonRpcTransportPort(Protocol):
    """A sandbox-local transport adapter that returns decoded JSON-RPC results."""

    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """Send one JSON-RPC request and return only its successful ``result`` object."""

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        """Send one JSON-RPC notification."""

    def set_protocol_version(self, protocol_version: str) -> None:
        """Configure the negotiated protocol version for subsequent transport requests."""

    def close(self) -> None:
        """Close the underlying stdio or HTTP session and release sandbox resources."""


@dataclass(frozen=True, slots=True)
class McpHostProbeResult:
    """Negotiated session facts plus the normalized inventory captured by the host."""

    transcript: McpProbeTranscript
    server_version: str | None
    server_capabilities: Mapping[str, Any]
    tools_list_changed: bool
    resources_list_changed: bool
    prompts_list_changed: bool
    ping_succeeded: bool

    def __post_init__(self) -> None:
        if not isinstance(self.transcript, McpProbeTranscript):
            raise McpHostProbeError("host probe result requires an MCP probe transcript")
        if self.server_version is not None and (
            not isinstance(self.server_version, str) or not self.server_version.strip()
        ):
            raise McpHostProbeError("server version must be a non-empty string when supplied")
        if not isinstance(self.server_capabilities, Mapping):
            raise McpHostProbeError("server capabilities must be an object")
        object.__setattr__(self, "server_capabilities", freeze_mapping(self.server_capabilities))
        for field_name in (
            "tools_list_changed",
            "resources_list_changed",
            "prompts_list_changed",
            "ping_succeeded",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise McpHostProbeError(f"{field_name} must be a boolean")


class McpHostProtocolProbe:
    """Execute the mandatory MCP probe lifecycle over one isolated transport."""

    def __init__(
        self,
        transport: McpJsonRpcTransportPort,
        *,
        client_name: str = "ForgeAI",
        client_version: str = "0.1.0",
        supported_protocol_versions: tuple[str, ...] = ("2025-11-25",),
        max_list_pages: int = 10,
        require_ping: bool = True,
    ) -> None:
        if not isinstance(client_name, str) or not client_name.strip():
            raise ValueError("client_name must be a non-empty string")
        if not isinstance(client_version, str) or not client_version.strip():
            raise ValueError("client_version must be a non-empty string")
        versions = tuple(supported_protocol_versions)
        if not versions or any(
            not isinstance(version, str) or not _PROTOCOL_VERSION_PATTERN.fullmatch(version)
            for version in versions
        ):
            raise ValueError("supported_protocol_versions must contain MCP date versions")
        if len(set(versions)) != len(versions):
            raise ValueError("supported_protocol_versions must be unique")
        if not 1 <= max_list_pages <= 100:
            raise ValueError("max_list_pages must be between 1 and 100")
        if not isinstance(require_ping, bool):
            raise ValueError("require_ping must be a boolean")
        self._transport = transport
        self._client_name = client_name.strip()
        self._client_version = client_version.strip()
        self._supported_versions = versions
        self._max_list_pages = max_list_pages
        self._require_ping = require_ping

    def probe(
        self,
        *,
        plan: McpInstallationPlan,
        execution: McpProbeExecutionEvidence,
    ) -> McpHostProbeResult:
        """Perform initialize and inventory collection, then always close the probe transport."""

        if not plan.ready_for_sandbox_execution:
            raise McpHostProbeError("only sandbox-ready plans may enter the MCP host lifecycle")
        try:
            initialization = self._request_initialize()
            protocol_version, server_name, server_version, capabilities = self._parse_initialize(initialization)
            if protocol_version not in self._supported_versions:
                raise McpHostProbeError(
                    f"server negotiated unsupported protocol version {protocol_version!r}"
                )
            if server_name != plan.server_name:
                raise McpHostProbeError("MCP serverInfo.name does not match the planned server identity")
            self._transport.set_protocol_version(protocol_version)
            self._transport.notify("notifications/initialized", {})
            ping_succeeded = self._ping() if self._require_ping else False

            tools_capability = self._capability(capabilities, "tools")
            resources_capability = self._capability(capabilities, "resources")
            prompts_capability = self._capability(capabilities, "prompts")
            tools = (
                tuple(self._list_items("tools/list", "tools", self._tool))
                if tools_capability is not None
                else ()
            )
            resources = (
                tuple(self._list_items("resources/list", "resources", self._resource))
                if resources_capability is not None
                else ()
            )
            prompts = (
                tuple(self._list_items("prompts/list", "prompts", self._prompt))
                if prompts_capability is not None
                else ()
            )
            transcript = McpProbeTranscript(
                server_name=server_name,
                protocol_version=protocol_version,
                transport=plan.transport,
                execution=execution,
                tools=tools,
                resources=resources,
                prompts=prompts,
                # An absent optional server capability is a complete empty inventory;
                # an advertised capability is listed through its paginated method.
                tools_listed=True,
                resources_listed=True,
                prompts_listed=True,
            )
            return McpHostProbeResult(
                transcript=transcript,
                server_version=server_version,
                server_capabilities=capabilities,
                tools_list_changed=self._list_changed(tools_capability),
                resources_list_changed=self._list_changed(resources_capability),
                prompts_list_changed=self._list_changed(prompts_capability),
                ping_succeeded=ping_succeeded,
            )
        finally:
            self._transport.close()

    def _request_initialize(self) -> Mapping[str, Any]:
        return self._transport.request(
            "initialize",
            {
                "protocolVersion": self._supported_versions[0],
                # A discovery probe deliberately advertises no roots, sampling,
                # elicitation, or other privileged client capabilities.
                "capabilities": {},
                "clientInfo": {"name": self._client_name, "version": self._client_version},
            },
        )

    def _ping(self) -> bool:
        result = self._transport.request("ping", {})
        if not isinstance(result, Mapping):
            raise McpHostProbeError("ping result must be an object")
        return True

    @staticmethod
    def _parse_initialize(
        response: Mapping[str, Any],
    ) -> tuple[str, str, str | None, Mapping[str, Any]]:
        if not isinstance(response, Mapping):
            raise McpHostProbeError("initialize result must be an object")
        protocol_version = response.get("protocolVersion")
        if not isinstance(protocol_version, str) or not _PROTOCOL_VERSION_PATTERN.fullmatch(protocol_version):
            raise McpHostProbeError("initialize result must contain a date-based protocolVersion")
        server_info = response.get("serverInfo")
        if not isinstance(server_info, Mapping):
            raise McpHostProbeError("initialize result must contain serverInfo")
        server_name = server_info.get("name")
        if not isinstance(server_name, str) or not server_name.strip():
            raise McpHostProbeError("serverInfo.name must be a non-empty string")
        server_version = server_info.get("version")
        if server_version is not None and (not isinstance(server_version, str) or not server_version.strip()):
            raise McpHostProbeError("serverInfo.version must be a non-empty string when supplied")
        capabilities = response.get("capabilities")
        if not isinstance(capabilities, Mapping):
            raise McpHostProbeError("initialize result must contain a capabilities object")
        return protocol_version, server_name.strip(), server_version.strip() if server_version else None, capabilities

    @staticmethod
    def _capability(capabilities: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
        value = capabilities.get(name)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise McpHostProbeError(f"server capability {name!r} must be an object")
        return value

    @staticmethod
    def _list_changed(capability: Mapping[str, Any] | None) -> bool:
        if capability is None:
            return False
        value = capability.get("listChanged", False)
        if not isinstance(value, bool):
            raise McpHostProbeError("MCP listChanged capability values must be booleans")
        return value

    def _list_items(
        self,
        method: str,
        key: str,
        parser: Any,
    ) -> list[_Item]:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        items: list[_Item] = []
        for _ in range(self._max_list_pages):
            params: dict[str, str] = {} if cursor is None else {"cursor": cursor}
            response = self._transport.request(method, params)
            if not isinstance(response, Mapping):
                raise McpHostProbeError(f"{method} result must be an object")
            raw_items = response.get(key)
            if not isinstance(raw_items, list):
                raise McpHostProbeError(f"{method} result must contain a {key} array")
            for item in raw_items:
                if not isinstance(item, Mapping):
                    raise McpHostProbeError(f"{method} {key} entries must be objects")
                try:
                    items.append(parser(item))
                except (TypeError, ValueError) as error:
                    raise McpHostProbeError(f"{method} returned an invalid {key} entry") from error
            next_cursor = response.get("nextCursor")
            if next_cursor is None:
                return items
            if not isinstance(next_cursor, str) or not next_cursor.strip():
                raise McpHostProbeError(f"{method} nextCursor must be a non-empty string when supplied")
            if next_cursor in seen_cursors:
                raise McpHostProbeError(f"{method} returned a repeated pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise McpHostProbeError(f"{method} exceeded the configured pagination limit")

    @staticmethod
    def _tool(value: Mapping[str, Any]) -> McpToolDescriptor:
        input_schema = value.get("inputSchema")
        if not isinstance(input_schema, Mapping):
            raise McpHostProbeError("tools/list entries must contain an inputSchema object")
        output_schema = value.get("outputSchema")
        if output_schema is not None and not isinstance(output_schema, Mapping):
            raise McpHostProbeError("tools/list outputSchema must be an object when supplied")
        annotations = value.get("annotations", {})
        if not isinstance(annotations, Mapping):
            raise McpHostProbeError("tools/list annotations must be an object when supplied")
        description = value.get("description")
        if description is not None and not isinstance(description, str):
            raise McpHostProbeError("tools/list description must be a string when supplied")
        return McpToolDescriptor(
            name=value.get("name"),
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            annotations=annotations,
        )

    @staticmethod
    def _resource(value: Mapping[str, Any]) -> McpResourceDescriptor:
        description = value.get("description")
        mime_type = value.get("mimeType")
        if description is not None and not isinstance(description, str):
            raise McpHostProbeError("resources/list description must be a string when supplied")
        if mime_type is not None and not isinstance(mime_type, str):
            raise McpHostProbeError("resources/list mimeType must be a string when supplied")
        return McpResourceDescriptor(
            uri=value.get("uri"),
            name=value.get("name"),
            description=description,
            mime_type=mime_type,
        )

    @staticmethod
    def _prompt(value: Mapping[str, Any]) -> McpPromptDescriptor:
        description = value.get("description")
        if description is not None and not isinstance(description, str):
            raise McpHostProbeError("prompts/list description must be a string when supplied")
        return McpPromptDescriptor(name=value.get("name"), description=description)
