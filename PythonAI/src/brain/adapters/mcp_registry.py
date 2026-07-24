"""Read-only, policy-neutral discovery adapter for the Official MCP Registry.

The adapter only fetches and normalizes registry metadata. It cannot install a
package, start an MCP server, invoke a tool, or resolve a secret. This keeps
metadata discovery independent from the later installation and execution trust
domains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..domain.models import freeze_mapping
from ..mcp.server_manifest import McpServerManifest, ServerManifestValidationError, parse_server_manifest


OFFICIAL_REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io/v0.1"
OFFICIAL_REGISTRY_HOST = "registry.modelcontextprotocol.io"
OFFICIAL_METADATA_KEY = "io.modelcontextprotocol.registry/official"


class RegistryFetchError(RuntimeError):
    """Raised when registry metadata cannot be fetched safely or decoded."""


class _NoRedirect(HTTPRedirectHandler):
    """Prevent a configured registry host from redirecting discovery elsewhere."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> Request | None:
        return None


JsonFetcher = Callable[[str, float, int], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class RegistryServerObservation:
    """A server document plus registry-specific, non-authoritative metadata."""

    manifest: McpServerManifest
    source_url: str
    raw_metadata_hash: str
    registry_id: str | None = None
    status: str | None = None
    is_latest: bool | None = None
    published_at: str | None = None
    registry_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_metadata", freeze_mapping(self.registry_metadata or {}))

    @property
    def eligible_for_activation(self) -> bool:
        """Deprecated/deleted registry entries cannot become active automatically."""

        return self.status in {None, "active"}


@dataclass(frozen=True, slots=True)
class RegistryDiscoveryError:
    """An invalid server entry that does not invalidate a whole registry page."""

    index: int
    message: str


@dataclass(frozen=True, slots=True)
class RegistryDiscoveryPage:
    """A cursor page fetched from a registry endpoint."""

    observations: tuple[RegistryServerObservation, ...]
    errors: tuple[RegistryDiscoveryError, ...]
    next_cursor: str | None
    total: int | None


class OfficialMcpRegistrySource:
    """Fetch one official/explicitly allowlisted MCP Registry page at a time."""

    def __init__(
        self,
        *,
        base_url: str = OFFICIAL_REGISTRY_BASE_URL,
        allowed_hosts: frozenset[str] | None = None,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 2_000_000,
        fetch_json: JsonFetcher | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        parsed = urlparse(base_url)
        allowed = allowed_hosts or frozenset({OFFICIAL_REGISTRY_HOST})
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("registry base_url must be an absolute HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("registry base_url may not embed user credentials")
        if parsed.hostname not in allowed:
            raise ValueError("registry base_url host is not explicitly allowlisted")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._fetch_json = fetch_json or self._urllib_fetch_json

    def list_servers(
        self,
        *,
        search: str | None = None,
        cursor: str | None = None,
        limit: int = 25,
    ) -> RegistryDiscoveryPage:
        """Fetch and normalize one registry page, retaining per-entry failures."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if search is not None and not search.strip():
            raise ValueError("search must be non-empty when supplied")
        if cursor is not None and not cursor.strip():
            raise ValueError("cursor must be non-empty when supplied")
        query: dict[str, str | int] = {"limit": limit}
        if search is not None:
            query["search"] = search.strip()
        if cursor is not None:
            query["cursor"] = cursor.strip()
        url = f"{self._base_url}/servers?{urlencode(query)}"
        document = self._fetch_json(url, self._timeout_seconds, self._max_response_bytes)
        return self._parse_page(document, source_url=url)

    @staticmethod
    def _urllib_fetch_json(url: str, timeout_seconds: float, max_response_bytes: int) -> Mapping[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "ForgeAI-MCP-Discovery/0.1",
            },
            method="GET",
        )
        try:
            opener = build_opener(_NoRedirect())
            with opener.open(request, timeout=timeout_seconds) as response:
                response_bytes = response.read(max_response_bytes + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise RegistryFetchError(f"registry request failed: {error}") from error
        if len(response_bytes) > max_response_bytes:
            raise RegistryFetchError("registry response exceeded the configured safety limit")
        try:
            document = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RegistryFetchError("registry response was not valid UTF-8 JSON") from error
        if not isinstance(document, Mapping):
            raise RegistryFetchError("registry response root must be a JSON object")
        return document

    @staticmethod
    def _parse_page(document: Mapping[str, Any], *, source_url: str) -> RegistryDiscoveryPage:
        servers_value = document.get("servers")
        if not isinstance(servers_value, list):
            raise RegistryFetchError("registry response must contain a servers array")
        metadata_value = document.get("metadata", {})
        metadata = metadata_value if isinstance(metadata_value, Mapping) else {}
        next_cursor = metadata.get("next_cursor", document.get("next_cursor"))
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise RegistryFetchError("registry next_cursor must be a string when supplied")
        total = metadata.get("total", document.get("total"))
        if total is not None and (not isinstance(total, int) or isinstance(total, bool)):
            raise RegistryFetchError("registry total must be an integer when supplied")

        observations: list[RegistryServerObservation] = []
        errors: list[RegistryDiscoveryError] = []
        for index, entry in enumerate(servers_value):
            try:
                if not isinstance(entry, Mapping):
                    raise ServerManifestValidationError("server entry must be an object")
                server_document = entry.get("server", entry)
                if not isinstance(server_document, Mapping):
                    raise ServerManifestValidationError("server entry.server must be an object")
                official_metadata = OfficialMcpRegistrySource._official_metadata(entry)
                status = OfficialMcpRegistrySource._optional_text(
                    official_metadata.get("status", entry.get("status")), "status"
                )
                is_latest = official_metadata.get("is_latest", entry.get("is_latest"))
                if is_latest is not None and not isinstance(is_latest, bool):
                    raise ServerManifestValidationError("is_latest must be a boolean when supplied")
                published_at = OfficialMcpRegistrySource._optional_text(
                    official_metadata.get("published_at", entry.get("published_at")), "published_at"
                )
                registry_id = OfficialMcpRegistrySource._optional_text(
                    official_metadata.get("id", entry.get("id")), "id"
                )
                canonical = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
                observations.append(
                    RegistryServerObservation(
                        manifest=parse_server_manifest(server_document, source_url=source_url),
                        source_url=source_url,
                        raw_metadata_hash=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
                        registry_id=registry_id,
                        status=status,
                        is_latest=is_latest,
                        published_at=published_at,
                        registry_metadata=official_metadata,
                    )
                )
            except (ServerManifestValidationError, TypeError, ValueError) as error:
                errors.append(RegistryDiscoveryError(index=index, message=str(error)))
        return RegistryDiscoveryPage(
            observations=tuple(observations),
            errors=tuple(errors),
            next_cursor=next_cursor,
            total=total,
        )

    @staticmethod
    def _official_metadata(entry: Mapping[str, Any]) -> Mapping[str, Any]:
        raw_meta = entry.get("_meta", {})
        if not isinstance(raw_meta, Mapping):
            return {}
        official = raw_meta.get(OFFICIAL_METADATA_KEY, {})
        return official if isinstance(official, Mapping) else {}

    @staticmethod
    def _optional_text(value: Any, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ServerManifestValidationError(f"{field_name} must be a non-empty string when supplied")
        return value.strip()
