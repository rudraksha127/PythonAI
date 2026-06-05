"""
PythonAI Web UI — Provider Routing Dashboard
==============================================
Visualize provider status, routing strategies, model availability,
and API key configuration in real-time.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render() -> None:
    """Render the provider routing dashboard page."""
    st.markdown("""
    <style>
    .prov-card {
        background: rgba(28, 28, 40, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 0.7rem 1rem;
        margin: 0.3rem 0;
        transition: all 0.3s;
    }
    .prov-card:hover {
        border-color: rgba(0, 210, 255, 0.3);
    }
    .prov-online { border-left: 3px solid #51cf66; }
    .prov-offline { border-left: 3px solid #ff6b6b; opacity: 0.6; }
    .prov-local { border-left: 3px solid #f59f00; }
    .prov-name { font-weight: 700; font-size: 0.9rem; }
    .prov-status-on { color: #51cf66; font-size: 0.75rem; }
    .prov-status-off { color: #ff6b6b; font-size: 0.75rem; }
    .prov-model { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: rgba(255,255,255,0.5); }
    .route-box {
        background: rgba(0, 210, 255, 0.06);
        border: 1px solid rgba(0, 210, 255, 0.15);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .route-box .label { font-size: 0.7rem; color: rgba(255,255,255,0.4); text-transform: uppercase; }
    .route-box .value { font-size: 1rem; font-weight: 700; color: #00d2ff; }
    </style>
    """, unsafe_allow_html=True)

    st.title("Provider Routing Dashboard")
    st.caption("Multi-provider routing, model availability, and API key configuration")

    # ── Current Route ──
    _render_current_route()

    # ── All Providers ──
    _render_provider_list()

    # ── Models ──
    _render_model_catalog()

    # ── Profile / Strategy ──
    _render_profile_config()


def _render_current_route() -> None:
    """Show the currently active provider route."""
    st.markdown("### Active Route")

    try:
        from src.core.providers import ProviderRouter, ProfileManager

        router = ProviderRouter()
        profile_mgr = ProfileManager()

        profile = profile_mgr.load()
        provider_id = profile.provider if profile else "auto"
        model = profile.model if profile and profile.model else ""

        result = router.route(provider=provider_id, model=model or None)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f'<div class="route-box"><div class="label">Provider</div>'
                f'<div class="value">{result.provider or "N/A"}</div></div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f'<div class="route-box"><div class="label">Model</div>'
                f'<div class="value">{result.model or "auto"}</div></div>',
                unsafe_allow_html=True,
            )
        with col3:
            strategy = profile.strategy if profile else "auto"
            st.markdown(
                f'<div class="route-box"><div class="label">Strategy</div>'
                f'<div class="value">{strategy}</div></div>',
                unsafe_allow_html=True,
            )
        with col4:
            api_type = result.api_type or "openai"
            st.markdown(
                f'<div class="route-box"><div class="label">API Type</div>'
                f'<div class="value">{api_type}</div></div>',
                unsafe_allow_html=True,
            )

        if result.error:
            st.warning(f"Routing error: {result.error}")

    except Exception as e:
        st.info(f"Default route: auto (configure providers below). {e}")


def _render_provider_list() -> None:
    """Render list of all available providers with status."""
    st.markdown("### All Providers")

    try:
        from src.core.providers import ProviderRouter

        router = ProviderRouter()
        statuses = router.get_provider_status()

        if not statuses:
            st.info("No providers configured.")
            return

        for s in statuses:
            is_avail = s.get("available", False)
            is_local = s.get("is_local", False)
            cls = "prov-online" if is_avail else ("prov-local" if is_local else "prov-offline")
            status_text = "ONLINE" if is_avail else ("LOCAL" if is_local else "NO KEY")

            status_class = "prov-status-on" if is_avail else "prov-status-off"
        st.markdown(
            f'<div class="prov-card {cls}">'
            f'<div class="prov-name">{s.get("label", s["id"])}</div>'
            f'<div style="display:flex;justify-content:space-between;margin-top:0.2rem;">'
            f'<span class="prov-model">{s.get("default_model", "")}</span>'
            f'<span class="{status_class}">{status_text}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        online = sum(1 for s in statuses if s.get("available"))
        offline = sum(1 for s in statuses if not s.get("available") and not s.get("is_local"))
        local = sum(1 for s in statuses if s.get("is_local"))

        st.caption(f"{online} online | {local} local | {offline} no key")

    except Exception as e:
        st.error(f"Cannot load providers: {e}")


def _render_model_catalog() -> None:
    """Render model catalog filtered by provider."""
    st.markdown("### Model Catalog")

    try:
        from src.core.providers import ALL_MODELS

        if not ALL_MODELS:
            st.info("No models catalog available.")
            return

        providers = sorted(set(m.provider for m in ALL_MODELS))
        selected_provider = st.selectbox(
            "Filter by provider:",
            options=["All"] + providers,
            key="provider_filter",
        )

        models = ALL_MODELS
        if selected_provider != "All":
            models = [m for m in models if m.provider == selected_provider]

        st.markdown(f"**{len(models)} models**")

        import pandas as pd

        rows = []
        for m in models:
            caps = []
            if m.capabilities.vision:
                caps.append("vision")
            if m.capabilities.reasoning:
                caps.append("reasoning")
            if "coding" in m.classification:
                caps.append("coding")
            if m.capabilities.function_calling:
                caps.append("fn-call")
            rows.append({
                "Model": m.id,
                "Provider": m.provider,
                "Context": f"{m.context_window:,}",
                "Capabilities": ", ".join(caps) if caps else "chat",
                "Default": "[D]" if m.default_model else "",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.info(f"Model catalog not available: {e}")


def _render_profile_config() -> None:
    """Render provider profile configuration."""
    st.markdown("### Profile Configuration")

    try:
        from src.core.providers import ProfileManager, ProviderRouter

        profile_mgr = ProfileManager()
        profile = profile_mgr.load()

        if profile:
            st.markdown(f"- **Provider:** {profile.label} ({profile.provider})")
            st.markdown(f"- **Model:** {profile.model or '(default)'}")
            st.markdown(f"- **Strategy:** {profile.strategy}")
            st.markdown(f"- **Base URL:** {profile.base_url or '(default)'}")
            st.markdown(f"- **Saved at:** {profile_mgr.profile_path}")

            if st.button("Reset Profile", type="secondary"):
                profile_mgr.delete()
                st.success("Profile reset to auto-select")
                st.rerun()

            if st.button("Test Route", type="primary"):
                with st.spinner("Testing route..."):
                    try:
                        router = ProviderRouter()
                        result = router.route(
                            provider=profile.provider,
                            model=profile.model or None,
                        )
                        if result.error:
                            st.error(f"Route failed: {result.error}")
                        else:
                            st.success(
                                f"Route OK: {result.provider}/{result.model} "
                                f"via {result.base_url}"
                            )
                    except Exception as e:
                        st.error(f"Route test failed: {e}")
        else:
            st.info("No custom profile. Using auto-select routing.")
            st.markdown(
                "Set a provider with: `python -m src.cli provider switch <name>`"
            )

    except Exception as e:
        st.error(f"Cannot load profile: {e}")
