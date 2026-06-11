"""
Unit tests for src.core.mcp.transport — Backward Compatibility Re-exports.
"""

from __future__ import annotations


class TestTransportReExports:
    """Verify all expected re-exports exist and match types.py."""

    def test_import_transport_type(self) -> None:
        """TransportType enum is importable from transport module."""
        from src.core.mcp.transport import TransportType

        assert TransportType is not None

    def test_transport_type_values(self) -> None:
        """TransportType has expected values."""
        from src.core.mcp.transport import TransportType

        values = list(TransportType)
        assert any(v.value == "stdio" for v in values)
        assert any(v.value == "sse" for v in values)
        assert any(v.value == "http" for v in values)

    def test_import_stdio_config(self) -> None:
        """StdioConfig is importable and constructable."""
        from src.core.mcp.transport import StdioConfig

        cfg = StdioConfig(command="npx", args=["-y", "test"])
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "test"]

    def test_import_sse_config(self) -> None:
        """SSEConfig is importable and constructable."""
        from src.core.mcp.transport import SSEConfig

        cfg = SSEConfig(url="http://localhost:8080/sse")
        assert cfg.url == "http://localhost:8080/sse"

    def test_import_http_config(self) -> None:
        """HTTPConfig is importable and constructable."""
        from src.core.mcp.transport import HTTPConfig

        cfg = HTTPConfig(url="http://localhost:8080/api")
        assert cfg.url == "http://localhost:8080/api"

    def test_import_server_config(self) -> None:
        """ServerConfig is importable."""
        from src.core.mcp.transport import ServerConfig

        assert ServerConfig is not None

    def test_import_connection_state(self) -> None:
        """ConnectionState enum is importable and has expected states."""
        from src.core.mcp.transport import ConnectionState

        values = [v.value for v in ConnectionState]
        assert "connected" in values
        assert "failed" in values
        assert "pending" in values
        assert "disconnected" in values

    def test_import_server_connection(self) -> None:
        """ServerConnection is importable."""
        from src.core.mcp.transport import ServerConnection

        assert ServerConnection is not None

    def test_import_mcp_scope(self) -> None:
        """MCPScope enum is importable."""
        from src.core.mcp.transport import MCPScope

        assert MCPScope is not None

    def test_all_imports_match_types_module(self) -> None:
        """All re-exports from transport match those from types module."""
        from src.core.mcp.transport import (
            ConnectionState,
            HTTPConfig,
            MCPScope,
            ServerConfig,
            ServerConnection,
            SSEConfig,
            StdioConfig,
            TransportType,
        )
        from src.core.mcp.types import (  # noqa: N813
            ConnectionState as _cs,
        )
        from src.core.mcp.types import (  # noqa: N813
            HTTPConfig as _http,
        )
        from src.core.mcp.types import (  # noqa: N813
            MCPScope as _ms,
        )
        from src.core.mcp.types import (  # noqa: N813
            ServerConfig as _sc,
        )
        from src.core.mcp.types import (  # noqa: N813
            ServerConnection as _sc2,
        )
        from src.core.mcp.types import (  # noqa: N813
            SSEConfig as _sse,
        )
        from src.core.mcp.types import (  # noqa: N813
            StdioConfig as _stdio,
        )
        from src.core.mcp.types import (  # noqa: N813
            TransportType as _tt,
        )

        assert TransportType is _tt
        assert ServerConfig is _sc
        assert StdioConfig is _stdio
        assert SSEConfig is _sse
        assert HTTPConfig is _http
        assert ConnectionState is _cs
        assert ServerConnection is _sc2
        assert MCPScope is _ms
