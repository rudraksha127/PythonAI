"""Sandbox profiles for credential-free MCP probing.

The profile factory is a policy-enforcement boundary, not a container runtime.
An OCI, microVM, or OS-specific runner may implement the application port, but
it must honor this immutable profile before a package or remote endpoint can be
probed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from .installation import McpInstallTarget, McpInstallationPlan


class McpSandboxProfileError(ValueError):
    """Raised when a plan cannot receive ForgeAI's minimum isolation profile."""


class McpSandboxNetworkMode(str, Enum):
    """Probe networking is either absent or scoped to one verified remote origin."""

    NONE = "none"
    ORIGIN_ALLOWLIST = "origin-allowlist"


@dataclass(frozen=True, slots=True)
class McpProbeSandboxProfile:
    """Non-negotiable least-privilege constraints for one credential-free probe."""

    plan_id: str
    network_mode: McpSandboxNetworkMode
    allowed_origins: tuple[str, ...]
    read_only_root_filesystem: bool
    host_filesystem_access: bool
    credential_injection: bool
    privilege_escalation: bool
    maximum_runtime_seconds: int
    maximum_memory_megabytes: int
    maximum_processes: int

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise McpSandboxProfileError("sandbox.plan_id must be a non-empty string")
        if not isinstance(self.network_mode, McpSandboxNetworkMode):
            raise McpSandboxProfileError("sandbox.network_mode must be a supported network mode")
        object.__setattr__(self, "allowed_origins", tuple(self.allowed_origins))
        if any(not isinstance(origin, str) or not origin.strip() for origin in self.allowed_origins):
            raise McpSandboxProfileError("sandbox.allowed_origins must contain non-empty strings")
        if len(set(self.allowed_origins)) != len(self.allowed_origins):
            raise McpSandboxProfileError("sandbox.allowed_origins must be unique")
        if self.network_mode is McpSandboxNetworkMode.NONE and self.allowed_origins:
            raise McpSandboxProfileError("a no-network profile may not contain allowed origins")
        if self.network_mode is McpSandboxNetworkMode.ORIGIN_ALLOWLIST and len(self.allowed_origins) != 1:
            raise McpSandboxProfileError("an origin-allowlist profile requires exactly one origin")
        if self.network_mode is McpSandboxNetworkMode.ORIGIN_ALLOWLIST:
            for origin in self.allowed_origins:
                parsed = urlparse(origin)
                try:
                    parsed.port
                except ValueError as error:
                    raise McpSandboxProfileError("sandbox.allowed_origins may not use an invalid port") from error
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.path not in {"", "/"}
                    or parsed.params
                    or parsed.query
                    or parsed.fragment
                ):
                    raise McpSandboxProfileError(
                        "sandbox.allowed_origins must contain credential-free HTTPS origins only"
                    )
        for field_name in (
            "read_only_root_filesystem",
            "host_filesystem_access",
            "credential_injection",
            "privilege_escalation",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise McpSandboxProfileError(f"sandbox.{field_name} must be a boolean")
        if not self.read_only_root_filesystem:
            raise McpSandboxProfileError("MCP probe root filesystem must be read-only")
        if self.host_filesystem_access:
            raise McpSandboxProfileError("MCP probes may not access the host filesystem")
        if self.credential_injection:
            raise McpSandboxProfileError("MCP probes must not receive credentials")
        if self.privilege_escalation:
            raise McpSandboxProfileError("MCP probes may not allow privilege escalation")
        bounds = {
            "maximum_runtime_seconds": (1, 300),
            "maximum_memory_megabytes": (16, 4_096),
            "maximum_processes": (1, 256),
        }
        for field_name, (minimum, maximum) in bounds.items():
            value = getattr(self, field_name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not minimum <= value <= maximum
            ):
                raise McpSandboxProfileError(
                    f"sandbox.{field_name} must be between {minimum} and {maximum}"
                )


class McpProbeSandboxProfileFactory:
    """Derive a strict profile only from a fully verified installation plan."""

    @staticmethod
    def for_plan(plan: McpInstallationPlan) -> McpProbeSandboxProfile:
        if not plan.ready_for_sandbox_execution:
            raise McpSandboxProfileError("only sandbox-ready installation plans may receive a probe profile")
        if plan.target is McpInstallTarget.PACKAGE:
            return McpProbeSandboxProfile(
                plan_id=plan.plan_id,
                network_mode=McpSandboxNetworkMode.NONE,
                allowed_origins=(),
                read_only_root_filesystem=True,
                host_filesystem_access=False,
                credential_injection=False,
                privilege_escalation=False,
                maximum_runtime_seconds=30,
                maximum_memory_megabytes=512,
                maximum_processes=32,
            )
        if plan.target is McpInstallTarget.REMOTE:
            origin = McpProbeSandboxProfileFactory._remote_origin(plan.target_reference.locator)
            return McpProbeSandboxProfile(
                plan_id=plan.plan_id,
                network_mode=McpSandboxNetworkMode.ORIGIN_ALLOWLIST,
                allowed_origins=(origin,),
                read_only_root_filesystem=True,
                host_filesystem_access=False,
                credential_injection=False,
                privilege_escalation=False,
                maximum_runtime_seconds=30,
                maximum_memory_megabytes=256,
                maximum_processes=16,
            )
        raise McpSandboxProfileError(f"unsupported MCP installation target {plan.target!r}")

    @staticmethod
    def _remote_origin(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise McpSandboxProfileError("remote MCP probe origin must use HTTPS")
        if parsed.username or parsed.password:
            raise McpSandboxProfileError("remote MCP probe origin may not contain URL userinfo")
        default_port = 443
        try:
            port = parsed.port or default_port
        except ValueError as error:
            raise McpSandboxProfileError("remote MCP probe origin has an invalid port") from error
        host = parsed.hostname.lower()
        return f"https://{host}" if port == default_port else f"https://{host}:{port}"
