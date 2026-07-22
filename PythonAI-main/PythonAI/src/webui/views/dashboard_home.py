"""
PythonAI Web UI — Dashboard Home
=================================
Overview page combining tool system status, provider routing display,
and MCP server status into a single integrated dashboard.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from ..utils import inject_dashboard_css, load_registry, metric_card
except ImportError:
    from src.webui.utils import inject_dashboard_css, load_registry, metric_card


def render() -> None:
    """Render the main dashboard overview page."""
    inject_dashboard_css()

    # ── Header ──
    st.title("PythonAI Dashboard")
    st.caption("Real-time overview of Tool System, Provider Routing & MCP Connections")

    # ── Key Metrics Row ──
    metrics = _collect_metrics()
    cols = st.columns(4)
    metric_card(cols[0], "Tools Registered", str(metrics["total_tools"]), "Built-in + MCP")
    metric_card(cols[1], "Providers", f"{metrics['available_providers']}/{metrics['total_providers']}", "With API keys")
    metric_card(cols[2], "MCP Servers", str(metrics["mcp_servers"]), "Connected")
    metric_card(cols[3], "Models Known", str(metrics["known_models"]), "Across all providers")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── System Status Grid ──
    left_col, right_col = st.columns(2)

    with left_col:
        _render_tool_system_status()
        _render_provider_status()

    with right_col:
        _render_mcp_status()
        _render_engine_status()


def _collect_metrics() -> dict[str, Any]:
    """Collect key metrics from all systems."""
    metrics = {
        "total_tools": 0,
        "available_providers": 0,
        "total_providers": 0,
        "mcp_servers": 0,
        "known_models": 0,
    }

    try:
        reg = load_registry()
        if reg:
            metrics["total_tools"] = reg.total_count
    except Exception:
        pass

    try:
        from src.core.providers import ProviderRouter, get_registry

        reg = get_registry()
        metrics["known_models"] = len(reg.list_models())

        router = ProviderRouter()
        statuses = router.get_provider_status()
        available = [s for s in statuses if s.get("available")]
        metrics["available_providers"] = len(available)
        metrics["total_providers"] = len(statuses)
    except Exception:
        pass

    try:
        from src.core.mcp import MCPConfigManager

        mgr = MCPConfigManager()
        metrics["mcp_servers"] = len(mgr.get_servers())
    except Exception:
        pass

    return metrics


def _render_tool_system_status() -> None:
    """Render tool system status card."""
    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">Tool System</div>', unsafe_allow_html=True)

    try:
        from src.core.registry import get_registry

        reg = get_registry()

        st.markdown(f"- **Built-in tools:** {reg.builtin_count}")
        st.markdown(f"- **MCP tools:** {reg.mcp_count}")
        st.markdown(f"- **Total:** {reg.total_count}")

        # Show tool names
        if reg.total_count > 0:
            tools = reg.list_all()
            with st.expander("Tool List", expanded=False):
                for t in tools:
                    ro = " [RO]" if t.is_readonly() else ""
                    cs = " [CS]" if t.is_concurrency_safe() else ""
                    st.markdown(f"- `{t.name}`{ro}{cs}")
    except Exception as e:
        st.error(f"Cannot load tool system: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


def _render_provider_status() -> None:
    """Render provider routing status card."""
    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">Provider Routing</div>', unsafe_allow_html=True)

    try:
        from src.core.providers import ProviderRouter

        router = ProviderRouter()
        statuses = router.get_provider_status()

        for s in statuses:
            icon = "+" if s.get("available") else "-"
            label = s.get("label", s["id"])
            model = s.get("default_model", "")
            st.markdown(f"- `{icon}` **{label}** `{model}`")
    except Exception as e:
        st.error(f"Cannot load providers: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


def _render_mcp_status() -> None:
    """Render MCP server status card."""
    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">MCP Servers</div>', unsafe_allow_html=True)

    try:
        from src.core.mcp import MCPConfigManager

        mgr = MCPConfigManager()
        servers = mgr.get_servers()

        if servers:
            for name, config in servers.items():
                from src.core.mcp import HTTPConfig, SSEConfig, StdioConfig

                if isinstance(config, StdioConfig):
                    ttype = f"stdio ({config.command})"
                elif isinstance(config, SSEConfig):
                    ttype = "sse"
                elif isinstance(config, HTTPConfig):
                    ttype = "http"
                else:
                    ttype = "unknown"
                st.markdown(f"- `{name}` (`{ttype}`)")

            with st.expander("Config Files", expanded=False):
                from src.core.mcp import find_mcp_json_files

                files = find_mcp_json_files()
                for f in files:
                    st.markdown(f"- `{f}`")
        else:
            st.markdown("No MCP servers configured.")
            st.markdown("Add one with: `python -m src.cli mcp add <name> --command <cmd>`")

        st.markdown(f"**Total:** {len(servers)} server(s) configured")
    except Exception as e:
        st.error(f"Cannot load MCP config: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


def _render_engine_status() -> None:
    """Render engine status card."""
    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
    st.markdown('<div class="card-header">Execution Engine</div>', unsafe_allow_html=True)

    try:
        from src.core.executor import QueryConfig

        config = QueryConfig()
        st.markdown(f"- **Max tool rounds:** {config.max_tool_rounds}")
        st.markdown(f"- **Context window:** {config.model_context_window:,} tokens")
        st.markdown(f"- **Parallel tools:** {'Enabled' if config.enable_parallel_tools else 'Disabled'}")
        st.markdown(f"- **Auto-compact:** {'Enabled' if config.enable_auto_compact else 'Disabled'}")
        st.markdown(f"- **Token budget:** {'Enabled' if config.enable_token_budget else 'Disabled'}")
        st.markdown(f"- **Model fallback:** {'Enabled' if config.enable_model_fallback else 'Disabled'}")
    except Exception as e:
        st.error(f"Cannot load engine: {e}")

    st.markdown("</div>", unsafe_allow_html=True)
