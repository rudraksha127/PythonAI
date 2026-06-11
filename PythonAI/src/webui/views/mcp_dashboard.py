"""
PythonAI Web UI — MCP Server Dashboard
========================================
Visualize MCP server connections, tools, resources, and manage
MCP configurations in real-time.
"""

from __future__ import annotations

import streamlit as st


def render() -> None:
    """Render the MCP server status dashboard page."""
    st.markdown("""
    <style>
    .mcp-card {
        background: rgba(28, 28, 40, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 0.8rem 1rem;
        margin: 0.4rem 0;
        transition: all 0.3s;
    }
    .mcp-card:hover {
        border-color: rgba(123, 47, 247, 0.3);
    }
    .mcp-connected { border-left: 3px solid #51cf66; }
    .mcp-failed { border-left: 3px solid #ff6b6b; }
    .mcp-pending { border-left: 3px solid #f59f00; }
    .mcp-disabled { border-left: 3px solid rgba(255,255,255,0.2); opacity: 0.5; }
    .mcp-name { font-weight: 700; font-size: 0.9rem; color: #9775fa; }
    .mcp-tool { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
    .mcp-status { font-size: 0.72rem; }
    .status-connected { color: #51cf66; }
    .status-failed { color: #ff6b6b; }
    .status-pending { color: #f59f00; }
    </style>
    """, unsafe_allow_html=True)

    st.title("MCP Server Dashboard")
    st.caption("External tool connectivity via Model Context Protocol")

    # ── Server Configuration ──
    _render_mcp_config()

    # ── Connect & Discover ──
    col1, col2 = st.columns(2)
    with col1:
        _render_connection_panel()
    with col2:
        _render_config_files()


def _render_mcp_config() -> None:
    """Render MCP server configuration status."""
    st.markdown("### Configured Servers")

    try:
        from src.core.mcp import HTTPConfig, MCPConfigManager, SSEConfig, StdioConfig

        mgr = MCPConfigManager()
        servers = mgr.get_servers()

        if not servers:
            st.info("No MCP servers configured.")
            st.markdown("""
            Add an MCP server:
            ```bash
            python -m src.cli mcp add my-server --command npx --args -y @server/name
            python -m src.cli mcp connect --server my-server
            ```
            """)
            return

        # Summary stats
        cols = st.columns(3)
        cols[0].metric("Total Servers", len(servers))
        stdio_count = sum(1 for c in servers.values() if isinstance(c, StdioConfig))
        remote_count = sum(1 for c in servers.values() if isinstance(c, (SSEConfig, HTTPConfig)))
        cols[1].metric("Stdio", stdio_count)
        cols[2].metric("Remote", remote_count)

        for name, config in servers.items():
            if isinstance(config, StdioConfig):
                ttype = f"`{config.command}`"
                desc = f"args: {config.args[:3]}..."
            elif isinstance(config, SSEConfig):
                ttype = "SSE"
                desc = config.url
            elif isinstance(config, HTTPConfig):
                ttype = "HTTP"
                desc = config.url
            else:
                ttype = "?"
                desc = str(config)

            with st.expander(f"{name} ({ttype})", expanded=False):
                st.markdown(f"**Type:** {ttype}")
                st.markdown(f"**Config:** {desc}")
                if isinstance(config, StdioConfig) and config.env:
                    st.markdown(f"**Env vars:** {list(config.env.keys())}")

                # Try connect button
                if st.button("Connect", key=f"connect_{name}"):
                    with st.spinner(f"Connecting to {name}..."):
                        from src.core.mcp import MCPClient
                        client = MCPClient()
                        conn = client.connect(config, name)

                        if conn.state.value == "connected":
                            st.success(
                                f"Connected! {len(conn.tools)} tools, {len(conn.resources)} resources"
                            )

                            # Show tools
                            if conn.tools:
                                st.markdown("**Tools:**")
                                for t in conn.tools:
                                    st.markdown(
                                        f'<div class="mcp-tool">- {t.name}: {t.description[:60]}</div>',
                                        unsafe_allow_html=True,
                                    )

                            # Register in registry
                            from src.core.registry import get_registry
                            reg = get_registry()
                            count = reg.register_mcp_server(conn)
                            st.success(f"{count} MCP tools registered in PythonAI tool system")
                        else:
                            st.error(f"Connection failed: {conn.error or 'unknown error'}")

    except Exception as e:
        st.error(f"Cannot load MCP config: {e}")


def _render_connection_panel() -> None:
    """Render connection actions panel."""
    st.markdown("### Connection Manager")

    try:
        from src.core.mcp import MCPConfigManager
        from src.core.registry import get_registry

        mgr = MCPConfigManager()
        servers = mgr.get_servers()

        if not servers:
            st.info("Configure a server first to connect.")
            return

        # Quick-connect all button
        if st.button("Connect All Servers", type="primary", use_container_width=True):
            from src.core.mcp import MCPClient

            client = MCPClient()
            results = []
            for name, config in servers.items():
                with st.spinner(f"Connecting to {name}..."):
                    conn = client.connect(config, name)
                    results.append((name, conn))

            # Show results
            connected = sum(1 for _, c in results if c.state.value == "connected")
            st.success(f"{connected}/{len(results)} servers connected")

            for name, conn in results:
                if conn.state.value == "connected":
                    reg = get_registry()
                    count = reg.register_mcp_server(conn)
                    st.markdown(f"- {name}: {len(conn.tools)} tools, {count} registered")
                else:
                    st.markdown(f"- {name}: FAILED - {conn.error or '?'}")

        # Manual connect
        server_names = list(servers.keys())
        selected = st.selectbox("Connect specific server:", server_names, key="mcp_connect_select")

        if st.button(f"Connect '{selected}'", use_container_width=True):
            from src.core.mcp import MCPClient

            client = MCPClient()
            config = servers[selected]
            with st.spinner(f"Connecting to {selected}..."):
                conn = client.connect(config, selected)

                if conn.state.value == "connected":
                    st.success(f"{len(conn.tools)} tools, {len(conn.resources)} resources")
                    reg = get_registry()
                    reg.register_mcp_server(conn)
                else:
                    st.error(conn.error or "Failed")

        # Disconnect all
        if st.button("Clear All MCP Tools", use_container_width=True, type="secondary"):
            reg = get_registry()
            for name in servers:
                removed = reg.unregister_mcp_server(name)
                if removed:
                    st.markdown(f"- Removed {removed} tools from '{name}'")
            st.success("All MCP tools cleared from registry")

    except Exception as e:
        st.error(f"Connection error: {e}")


def _render_config_files() -> None:
    """Render MCP config files discovery panel."""
    st.markdown("### Config Files")

    try:
        from src.core.mcp import find_mcp_json_files

        files = find_mcp_json_files()

        if files:
            st.markdown(f"**{len(files)} config file(s) found:**")
            for f in files:
                size = f.stat().st_size if f.exists() else 0
                st.markdown(f"- `{f}` ({size} bytes)")

            # View file content
            selected_file = st.selectbox(
                "View config:",
                options=[str(f) for f in files],
                key="mcp_file_selector",
            )
            if selected_file:
                import json
                content = json.loads(Path(selected_file).read_text(encoding="utf-8"))
                st.json(content)
        else:
            st.info("No .mcp.json or mcp.json files found.")
            st.markdown("""
            Create a config file:
            ```json
            {
              "mcpServers": {
                "my-server": {
                  "command": "npx",
                  "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
                }
              }
            }
            ```
            """)

    except Exception as e:
        st.error(f"Config discovery error: {e}")


from pathlib import Path
