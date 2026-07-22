"""
PythonAI Web UI — Shared Utilities
====================================
Common helpers used across dashboard pages to avoid duplication.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

# ═══════════════════════════════════════
#  Registry Helper
# ═══════════════════════════════════════


def load_registry() -> Any | None:
    """Load and return the tool registry (lazy-initialized).

    Returns None if the core tool system is unavailable.
    """
    try:
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        reg = get_registry()
        try:
            register_all_tools(reg)
        except Exception:
            pass
        return reg
    except Exception:
        return None


def registry_metrics(registry: Any | None = None) -> dict[str, int]:
    """Get tool registry metrics as a dict."""
    if registry is None:
        registry = load_registry()
    if registry is None:
        return {"total": 0, "builtin": 0, "mcp": 0, "readonly": 0, "writable": 0}

    return {
        "total": registry.total_count,
        "builtin": registry.builtin_count,
        "mcp": registry.mcp_count,
        "readonly": len(registry.get_readonly()),
        "writable": len(registry.get_writable()),
    }


# ═══════════════════════════════════════
#  Metric Cards
# ═══════════════════════════════════════


def metric_card(
    container: Any,
    label: str,
    value: str,
    sub: str = "",
    large: bool = True,
) -> None:
    """Render a metric card with a value, label, and optional subtitle.

    Args:
        container: Streamlit column or container to render into.
        label: Metric label (e.g. "Tools Registered").
        value: Metric value (e.g. "14").
        sub: Optional subtitle / help text.
        large: If True, uses 2rem font; if False, uses 1.8rem.
    """
    font_size = "2rem" if large else "1.8rem"
    with container:
        st.markdown(
            f"""<div class="metric-box">
            <div class="metric-label">{label}</div>
            <div class="metric-value" style="font-size:{font_size}">{value}</div>
            {f'<div class="metric-sub">{sub}</div>' if sub else ""}
        </div>""",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════
#  Common CSS (injected once per page)
# ═══════════════════════════════════════

DASHBOARD_CSS = """
<style>
.metric-box {
    background: rgba(28, 28, 40, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 1rem;
    text-align: center;
    transition: all 0.3s;
}
.metric-box:hover {
    border-color: rgba(0, 210, 255, 0.3);
    box-shadow: 0 0 20px rgba(0, 210, 255, 0.1);
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 800;
    color: #00d2ff;
    font-family: 'JetBrains Mono', monospace;
}
.metric-label {
    font-size: 0.7rem;
    color: rgba(255, 255, 255, 0.5);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.3rem;
}
.metric-sub {
    font-size: 0.7rem;
    color: rgba(255, 255, 255, 0.35);
    margin-top: 0.2rem;
}
.tool-call-card {
    background: rgba(28, 28, 40, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin: 0.4rem 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    transition: all 0.3s;
}
.tool-call-card:hover {
    border-color: rgba(0, 210, 255, 0.3);
}
.tool-name {
    color: #00d2ff;
    font-weight: 700;
}
.tool-readonly {
    border-left: 3px solid #51cf66;
}
.tool-write {
    border-left: 3px solid #f59f00;
}
.tool-destructive {
    border-left: 3px solid #ff6b6b;
}
.stat-chip {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 600;
    margin: 2px;
}
.chip-ro { background: rgba(81,207,102,0.15); color: #51cf66; }
.chip-cs { background: rgba(0,210,255,0.15); color: #00d2ff; }
.chip-ds { background: rgba(255,107,107,0.15); color: #ff6b6b; }
.card-header {
    font-size: 1.1rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.status-online { color: #51cf66; font-weight: 600; }
.status-offline { color: #ff6b6b; font-weight: 600; }
</style>
"""


def inject_dashboard_css() -> None:
    """Inject common dashboard CSS into the page."""
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
