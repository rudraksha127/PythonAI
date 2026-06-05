"""
PythonAI Web UI — Tool Execution Dashboard
===========================================
Visualize tool calls, execution timing, concurrency batching,
and tool registry state in real-time.
"""

from __future__ import annotations

import json
import time
from typing import Any

import streamlit as st

try:
    from ..utils import inject_dashboard_css, load_registry, metric_card, registry_metrics
except ImportError:
    from src.webui.utils import inject_dashboard_css, load_registry, metric_card, registry_metrics


def render() -> None:
    """Render the tool execution dashboard page."""
    inject_dashboard_css()

    st.title("Tool Execution Dashboard")
    st.caption("Visualize tool registry, execution patterns, and concurrency batching")

    # ── Load Registry ──
    registry = load_registry()

    # ── Key Metrics ──
    if registry:
        metrics = registry_metrics(registry)
        metrics_cols = st.columns(5)
        metric_card(metrics_cols[0], "Total Tools", str(metrics["total"]), "registered", large=False)
        metric_card(metrics_cols[1], "Built-in", str(metrics["builtin"]), "core tools", large=False)
        metric_card(metrics_cols[2], "MCP", str(metrics["mcp"]), "external tools", large=False)
        metric_card(metrics_cols[3], "Read-only", str(metrics["readonly"]), "concurrency-safe", large=False)
        metric_card(metrics_cols[4], "Writable", str(metrics["writable"]), "serial execution", large=False)
    else:
        st.warning("Tool registry not available. Register tools first.")


def _render_all_tools(registry: Any) -> None:
    """Render all tools with their properties."""
    if not registry or registry.total_count == 0:
        st.info("No tools registered. Use tool-calling mode to register tools.")
        return

    tools = registry.list_all()
    st.markdown(f"**{len(tools)} tools** — ordered by name")

    for t in tools:
        cls = "tool-readonly" if t.is_readonly() else ("tool-destructive" if t.is_destructive() else "tool-write")
        chips = ""
        if t.is_readonly():
            chips += '<span class="stat-chip chip-ro">RO</span> '
        if t.is_concurrency_safe():
            chips += '<span class="stat-chip chip-cs">CS</span> '
        if t.is_destructive():
            chips += '<span class="stat-chip chip-ds">DEST</span> '

        st.markdown(
            f'<div class="tool-call-card {cls}">'
            f'<span class="tool-name">{t.name}</span> — {t.description[:80]} '
            f'<span style="float:right">{chips}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_readonly_tools(registry: Any) -> None:
    """Render read-only tools safe for parallel execution."""
    if not registry:
        return

    tools = registry.get_readonly()
    st.markdown(f"**{len(tools)} read-only tools** — safe for parallel execution")

    for t in tools:
        st.markdown(
            f'<div class="tool-call-card tool-readonly">'
            f'<span class="tool-name">{t.name}</span> — {t.description[:80]}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if len(tools) > 1:
        st.success(f"These {len(tools)} tools can execute in parallel using ThreadPoolExecutor (max 10 workers)")


def _render_writable_tools(registry: Any) -> None:
    """Render writable/destructive tools that run serially."""
    if not registry:
        return

    tools = registry.get_writable()
    st.markdown(f"**{len(tools)} writable tools** — serial execution required")

    for t in tools:
        cls = "tool-destructive" if t.is_destructive() else "tool-write"
        st.markdown(
            f'<div class="tool-call-card {cls}">'
            f'<span class="tool-name">{t.name}</span> — {t.description[:80]}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if len(tools) > 0:
        st.info("Writable tools are executed serially — one at a time, in order.")


def _render_tool_schema_viewer(registry: Any) -> None:
    """Render tool JSON Schema viewer."""
    if not registry:
        return

    tools = registry.list_all()
    selected_name = st.selectbox(
        "Select tool to view schema:",
        options=[t.name for t in tools],
        key="tool_schema_selector",
    )

    tool = registry.get(selected_name)
    if tool:
        schema = tool.to_openai_tool()
        st.json(schema, expanded=True)

        st.markdown("### Anthropic Format")
        anthro = tool.to_anthropic_tool()
        st.json(anthro, expanded=True)
