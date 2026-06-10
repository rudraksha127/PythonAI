"""
PythonAI Core — Base Tool Class
=================================
Inspired by Claude Code's Tool.ts architecture.
Provides typed tool interface with validation, permissions, and progress reporting.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, cast


# ═══════════════════════════════════════
#  Type Definitions
# ═══════════════════════════════════════

class PermissionDecision(str, Enum):
    """Result of a permission check."""
    ALLOW = "allow"
    DENY = "deny"
    ALWAYS_ALLOW = "always_allow"
    ALWAYS_DENY = "always_deny"
    ASK = "ask"


@dataclass
class ValidationResult:
    """Result of input validation."""
    success: bool
    message: str = ""
    error_code: int = 0


@dataclass
class PermissionResult:
    """Result of a permission check."""
    behavior: PermissionDecision = PermissionDecision.ALLOW
    message: str = ""
    updated_input: dict[str, Any] | None = None


@dataclass
class ToolResult:
    """Result of a tool execution."""
    data: Any
    error: str | None = None
    new_messages: list[dict[str, Any]] | None = None


@dataclass
class ToolProgress:
    """Progress update during tool execution."""
    tool_use_id: str
    data: dict[str, Any]


@dataclass
class ToolUseContext:
    """Context passed to every tool call."""
    cwd: str = ""
    verbose: bool = False
    debug: bool = False
    abort_signal: Callable[[], bool] = lambda: False
    env_vars: dict[str, str] = field(default_factory=dict)
    file_reading_limits: dict[str, int] = field(default_factory=lambda: {
        "max_tokens": 32000,
        "max_size_bytes": 5 * 1024 * 1024,  # 5MB
    })
    glob_limits: dict[str, int] = field(default_factory=lambda: {
        "max_results": 100,
    })


# ═══════════════════════════════════════
#  Input Schema (simplified JSON Schema)
# ═══════════════════════════════════════

@dataclass
class Parameter:
    """A single parameter definition for a tool's input schema."""
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str = ""
    default: Any = None
    required: bool = False
    enum: list[str] | None = None
    items: dict[str, Any] | None = None  # For array types


class InputSchema:
    """Simplified input schema definition."""

    def __init__(self, **params: Parameter):
        self._params = params

    @property
    def parameters(self) -> dict[str, Parameter]:
        return self._params

    def json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format (OpenAI tool calling format)."""
        properties = {}
        required = []

        for name, param in self._params.items():
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.items:
                prop["items"] = param.items
            if param.default is not None:
                prop["default"] = param.default

            properties[name] = prop
            if param.required:
                required.append(name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return schema

    def validate(self, input_data: dict[str, Any]) -> ValidationResult:
        """Validate input against schema."""
        for name, param in self._params.items():
            value = input_data.get(name)

            # Check required
            if param.required and value is None:
                return ValidationResult(
                    success=False,
                    message=f"Missing required parameter: '{name}'",
                    error_code=1,
                )

            # Check type
            if value is not None:
                type_map = {
                    "string": str,
                    "integer": int,
                    "boolean": bool,
                    "array": list,
                    "object": dict,
                }
                expected_type = type_map.get(param.type)
                if expected_type and not isinstance(value, expected_type):
                    return ValidationResult(
                        success=False,
                        message=f"Parameter '{name}' must be of type '{param.type}'",
                        error_code=2,
                    )

                # Check enum
                if param.enum and value not in param.enum:
                    return ValidationResult(
                        success=False,
                        message=f"Parameter '{name}' must be one of: {', '.join(param.enum)}",
                        error_code=3,
                    )

        return ValidationResult(success=True)


# ═══════════════════════════════════════
#  Base Tool Class
# ═══════════════════════════════════════

class Tool(ABC):
    """Base class for all PythonAI tools.

    Inspired by Claude Code's Tool<Input, Output, P> interface.
    """

    def __init__(self, name: str, description: str = ""):
        self._name = name
        self._description = description or f"{name} tool"
        self._aliases: list[str] = []
        self._search_hint: str = ""
        self._enabled: bool = True
        self._max_result_size_chars: int = 100000

    # ── Properties ───────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def aliases(self) -> list[str]:
        return self._aliases

    @property
    def search_hint(self) -> str:
        return self._search_hint

    @property
    def max_result_size_chars(self) -> int:
        return self._max_result_size_chars

    # ── Abstract Methods ─────────────────────────────────────

    @abstractmethod
    def input_schema(self) -> InputSchema:
        """Return the input schema for this tool."""
        ...

    @abstractmethod
    def call(self, input_data: dict[str, Any], context: ToolUseContext) -> ToolResult:
        """Execute the tool with given input and context."""
        ...

    def description_for_prompt(self, input_data: dict[str, Any] | None = None,
                                context: ToolUseContext | None = None) -> str:
        """Return the tool's description for the LLM prompt."""
        return self._description

    # ── Optional Override Methods ────────────────────────────

    def validate_input(self, input_data: dict[str, Any],
                       context: ToolUseContext) -> ValidationResult:
        """Validate input before execution. Default: schema validation."""
        return self.input_schema().validate(input_data)

    def check_permissions(self, input_data: dict[str, Any],
                          context: ToolUseContext) -> PermissionResult:
        """Check if this tool use is allowed. Default: always allow."""
        return PermissionResult(behavior=PermissionDecision.ALLOW)

    def is_readonly(self, input_data: dict[str, Any] | None = None) -> bool:
        """Is this tool read-only? Default: False."""
        return False

    def is_concurrency_safe(self, input_data: dict[str, Any] | None = None) -> bool:
        """Can this tool run in parallel with others? Default: False."""
        return False

    def is_destructive(self, input_data: dict[str, Any] | None = None) -> bool:
        """Does this tool perform irreversible operations? Default: False."""
        return False

    def is_enabled(self) -> bool:
        """Is this tool currently enabled? Default: True."""
        return self._enabled

    def user_facing_name(self, input_data: dict[str, Any] | None = None) -> str:
        """Human-readable name for UI display."""
        return self._name

    def get_tool_use_summary(self, input_data: dict[str, Any] | None = None) -> str | None:
        """Short summary for compact display."""
        return None

    def get_activity_description(self, input_data: dict[str, Any] | None = None) -> str | None:
        """Present-tense activity description for spinner display."""
        return None

    def to_auto_classifier_input(self, input_data: dict[str, Any]) -> Any:
        """Compact representation for security classifier."""
        return ""

    # ── Serialization ────────────────────────────────────────

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI tool calling format.

        MCP subclasses may override input_schema() to return a raw dict;
        this handles both standard InputSchema and raw dict returns.
        """
        schema = self.input_schema()
        # MCP tools may provide schema as a raw dict; cast at the call site.
        # Use a runtime isinstance check since subclasses can return dict.
        params: dict[str, Any]
        if isinstance(schema, dict):
            params = schema
        else:
            params = schema.json_schema()
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": params,
            }
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Convert to Anthropic tool use format."""
        return {
            "name": self._name,
            "description": self._description,
            "input_schema": {
                **self.input_schema().json_schema(),
            }
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize tool metadata."""
        return {
            "name": self._name,
            "description": self._description,
            "aliases": self._aliases,
            "search_hint": self._search_hint,
            "readonly": self.is_readonly(),
            "concurrency_safe": self.is_concurrency_safe(),
            "destructive": self.is_destructive(),
            "enabled": self.is_enabled(),
            "input_schema": self.input_schema().json_schema(),
        }


# ═══════════════════════════════════════
#  build_tool helper (inspired by Claude Code)
# ═══════════════════════════════════════

class ToolDef(Protocol):
    """Protocol for tool definitions passed to build_tool()."""
    name: str
    description: str
    input_schema: InputSchema
    call: Callable[[dict[str, Any], ToolUseContext], ToolResult]
    aliases: list[str] = []
    search_hint: str = ""
    max_result_size_chars: int = 100000
    validate_input: Callable[[dict[str, Any], ToolUseContext], ValidationResult] | None = None
    check_permissions: Callable[[dict[str, Any], ToolUseContext], PermissionResult] | None = None
    is_readonly: bool = False
    is_concurrency_safe: bool = False
    is_destructive: bool = False
    user_facing_name: Callable[[dict[str, Any] | None], str] | None = None
    get_tool_use_summary: Callable[[dict[str, Any] | None], str | None] | None = None
    get_activity_description: Callable[[dict[str, Any] | None], str | None] | None = None


class SimpleTool(Tool):
    """A concrete Tool built from a ToolDef via build_tool()."""

    # Typed callable references (set dynamically from defn)
    _call_fn: Callable[..., Any]
    _validate_fn: Callable[..., Any] | None
    _permissions_fn: Callable[..., Any] | None
    _user_facing_name_fn: Callable[..., Any] | None
    _summary_fn: Callable[..., Any] | None
    _activity_fn: Callable[..., Any] | None

    def __init__(self, defn: Any) -> None:
        super().__init__(defn.name, defn.description)
        self._input_schema: InputSchema = defn.input_schema
        # Unwrap callable attributes — they may be bound methods from
        # dynamically created classes (e.g. type('McpToolDef', (), {...})),
        # which would pass the defn instance as 'self' on invocation.
        self._call_fn = cast(Callable[..., Any], _unbind(defn.call))
        self._aliases: list[str] = getattr(defn, 'aliases', [])
        self._search_hint: str = getattr(defn, 'search_hint', '')
        self._max_result_size_chars: int = getattr(defn, 'max_result_size_chars', 100000)
        self._is_readonly: bool = getattr(defn, 'is_readonly', False)
        self._is_concurrency_safe: bool = getattr(defn, 'is_concurrency_safe', False)
        self._is_destructive: bool = getattr(defn, 'is_destructive', False)
        self._validate_fn = cast(Callable[..., Any] | None, _unbind(getattr(defn, 'validate_input', None)))
        self._permissions_fn = cast(Callable[..., Any] | None, _unbind(getattr(defn, 'check_permissions', None)))
        self._user_facing_name_fn = cast(Callable[..., Any] | None, _unbind(getattr(defn, 'user_facing_name', None)))
        self._summary_fn = cast(Callable[..., Any] | None, _unbind(getattr(defn, 'get_tool_use_summary', None)))
        self._activity_fn = cast(Callable[..., Any] | None, _unbind(getattr(defn, 'get_activity_description', None)))

    def input_schema(self) -> InputSchema:
        return self._input_schema

    def call(self, input_data: dict[str, Any], context: ToolUseContext) -> ToolResult:
        result = self._call_fn(input_data, context)
        return cast(ToolResult, result)

    def validate_input(self, input_data: dict[str, Any],
                       context: ToolUseContext) -> ValidationResult:
        if self._validate_fn:
            result = self._validate_fn(input_data, context)
            return cast(ValidationResult, result)
        return super().validate_input(input_data, context)

    def check_permissions(self, input_data: dict[str, Any],
                          context: ToolUseContext) -> PermissionResult:
        if self._permissions_fn:
            result = self._permissions_fn(input_data, context)
            return cast(PermissionResult, result)
        return super().check_permissions(input_data, context)

    def is_readonly(self, input_data: dict[str, Any] | None = None) -> bool:
        return self._is_readonly

    def is_concurrency_safe(self, input_data: dict[str, Any] | None = None) -> bool:
        return self._is_concurrency_safe

    def is_destructive(self, input_data: dict[str, Any] | None = None) -> bool:
        return self._is_destructive

    def user_facing_name(self, input_data: dict[str, Any] | None = None) -> str:
        if self._user_facing_name_fn:
            result = self._user_facing_name_fn(input_data)
            return cast(str, result)
        return self._name

    def get_tool_use_summary(self, input_data: dict[str, Any] | None = None) -> str | None:
        if self._summary_fn:
            result = self._summary_fn(input_data)
            return cast(str | None, result)
        return None

    def get_activity_description(self, input_data: dict[str, Any] | None = None) -> str | None:
        if self._activity_fn:
            result = self._activity_fn(input_data)
            return cast(str | None, result)
        return None


def _unbind(fn: Any) -> Any:
    """Unwrap a bound method to get the underlying function.

    When a callable is accessed on a class instance created via
    type('Name', (), {...})(), Python's descriptor protocol binds
    the method to the instance. Storing the bound method and
    calling it later passes the instance as 'self', adding an
    unexpected positional argument.
    """
    if fn is None:
        return None
    return getattr(fn, '__func__', fn)


TOOL_DEFAULTS = {
    "is_readonly": False,
    "is_concurrency_safe": False,
    "is_destructive": False,
    "max_result_size_chars": 100000,
    "aliases": [],
    "search_hint": "",
}


def build_tool(defn: Any) -> Tool:
    """Build a complete Tool from a partial definition.

    Inspired by Claude Code's buildTool() — fills in safe defaults.
    """
    # Apply defaults for missing attributes
    for key, value in TOOL_DEFAULTS.items():
        if not hasattr(defn, key):
            setattr(defn, key, value)

    return SimpleTool(defn)
