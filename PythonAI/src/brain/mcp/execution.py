"""Contracts for policy-bound MCP tool invocation.

Tool calls are intentionally separate from discovery and probing. Every call
must reference an immutable workflow plan and tool snapshot, go through a
policy decision point, and treat returned content as untrusted data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Mapping, Protocol
from uuid import uuid4

from ..domain.models import PolicyRequest, freeze_mapping
from ..domain.workflow import WorkflowPlan
from .probe import McpToolCatalogSnapshot


_MAX_ARGUMENT_BYTES = 128_000
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 10_000


class McpToolInvocationError(ValueError):
    """Raised when a call request or returned MCP payload violates the gateway contract."""


def _json_value(value: Any, *, field_name: str, depth: int = 0, nodes: list[int] | None = None) -> Any:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > _MAX_JSON_NODES:
        raise McpToolInvocationError(f"{field_name} exceeds the maximum JSON node count")
    if depth > _MAX_JSON_DEPTH:
        raise McpToolInvocationError(f"{field_name} exceeds the maximum JSON depth")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise McpToolInvocationError(f"{field_name} may not contain non-finite floats")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise McpToolInvocationError(f"{field_name} object keys must be strings")
            normalized[key] = _json_value(item, field_name=field_name, depth=depth + 1, nodes=nodes)
        return normalized
    if isinstance(value, (tuple, list)):
        return [_json_value(item, field_name=field_name, depth=depth + 1, nodes=nodes) for item in value]
    raise McpToolInvocationError(f"{field_name} must contain only JSON values")


def _canonical_json(value: Any, *, field_name: str, maximum_bytes: int) -> tuple[Any, bytes]:
    normalized = _json_value(value, field_name=field_name)
    try:
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:  # Defensive: _json_value should reject unsupported values.
        raise McpToolInvocationError(f"{field_name} cannot be JSON-encoded") from error
    if len(encoded) > maximum_bytes:
        raise McpToolInvocationError(f"{field_name} exceeds the configured size limit")
    return normalized, encoded


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class McpToolInvocationRequest:
    """A planned, policy-scoped request to invoke one tool from one snapshot."""

    workflow_plan: WorkflowPlan
    task_id: str
    snapshot: McpToolCatalogSnapshot
    tool_name: str
    arguments: Mapping[str, Any]
    policy_request: PolicyRequest
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_plan, WorkflowPlan):
            raise McpToolInvocationError("invocation.workflow_plan must be a workflow plan")
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise McpToolInvocationError("invocation.task_id must be a non-empty string")
        if not isinstance(self.snapshot, McpToolCatalogSnapshot):
            raise McpToolInvocationError("invocation.snapshot must be an MCP tool catalog snapshot")
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise McpToolInvocationError("invocation.tool_name must be a non-empty string")
        if not isinstance(self.policy_request, PolicyRequest):
            raise McpToolInvocationError("invocation.policy_request must be a policy request")
        if not isinstance(self.timeout_seconds, int) or isinstance(self.timeout_seconds, bool):
            raise McpToolInvocationError("invocation.timeout_seconds must be an integer")
        if not 1 <= self.timeout_seconds <= 120:
            raise McpToolInvocationError("invocation.timeout_seconds must be between 1 and 120")
        if not isinstance(self.arguments, Mapping):
            raise McpToolInvocationError("invocation.arguments must be a JSON object")
        normalized, _ = _canonical_json(
            self.arguments,
            field_name="invocation.arguments",
            maximum_bytes=_MAX_ARGUMENT_BYTES,
        )
        object.__setattr__(self, "arguments", freeze_mapping(normalized))


@dataclass(frozen=True, slots=True)
class McpToolInvocationResponse:
    """Untrusted tool output returned by an implementation-specific session invoker."""

    content: Any
    is_error: bool = False
    structured_content: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.is_error, bool):
            raise McpToolInvocationError("tool response is_error must be a boolean")
        normalized_content, _ = _canonical_json(
            self.content,
            field_name="tool response.content",
            maximum_bytes=_MAX_RESPONSE_BYTES,
        )
        object.__setattr__(self, "content", _freeze_json(normalized_content))
        if self.structured_content is not None:
            if not isinstance(self.structured_content, Mapping):
                raise McpToolInvocationError("tool response.structured_content must be an object")
            normalized_structured, _ = _canonical_json(
                self.structured_content,
                field_name="tool response.structured_content",
                maximum_bytes=_MAX_RESPONSE_BYTES,
            )
            object.__setattr__(self, "structured_content", freeze_mapping(normalized_structured))
        if not isinstance(self.metadata, Mapping):
            raise McpToolInvocationError("tool response.metadata must be an object")
        normalized_metadata, _ = _canonical_json(
            self.metadata,
            field_name="tool response.metadata",
            maximum_bytes=_MAX_ARGUMENT_BYTES,
        )
        object.__setattr__(self, "metadata", freeze_mapping(normalized_metadata))


@dataclass(frozen=True, slots=True)
class McpToolExecutionReceipt:
    """Hash-only audit companion for a tool response; content remains untrusted."""

    execution_id: str
    arguments_hash: str
    arguments_bytes: int
    output_hash: str
    output_bytes: int
    response: McpToolInvocationResponse
    untrusted_output: bool = True

    def __post_init__(self) -> None:
        for field_name in ("execution_id", "arguments_hash", "output_hash"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise McpToolInvocationError(f"receipt.{field_name} must be a non-empty string")
        for field_name in ("arguments_bytes", "output_bytes"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise McpToolInvocationError(f"receipt.{field_name} must be a non-negative integer")
        if not isinstance(self.response, McpToolInvocationResponse):
            raise McpToolInvocationError("receipt.response must be an MCP tool response")
        if self.untrusted_output is not True:
            raise McpToolInvocationError("MCP tool output must remain marked untrusted")


class McpToolInvokerPort(Protocol):
    """A live, sandboxed MCP host session that may call a selected snapshot tool."""

    def invoke(
        self,
        *,
        snapshot: McpToolCatalogSnapshot,
        tool_name: str,
        arguments: Mapping[str, Any],
        timeout_seconds: int,
    ) -> McpToolInvocationResponse:
        """Invoke exactly the named tool from the snapshot and return untrusted output."""


def new_execution_id() -> str:
    """Keep execution identity creation in the MCP contract layer."""

    return f"mcp-execution:{uuid4()}"


def payload_digest(value: Any, *, field_name: str, maximum_bytes: int) -> tuple[str, int]:
    """Return a stable content hash and byte size without logging raw payloads."""

    _, encoded = _canonical_json(value, field_name=field_name, maximum_bytes=maximum_bytes)
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}", len(encoded)
