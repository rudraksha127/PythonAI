"""
ForgeAI Acceptance Rate Dashboard — Streamlit View
===================================================

Real-time acceptance rate tracking, signal breakdown, and
training run history for the ForgeAI self-improvement loop.

Integrates with CaptureEngine SQLite database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

try:
    from ..utils import inject_dashboard_css, metric_card
except ImportError:
    from src.webui.utils import inject_dashboard_css, metric_card


def _get_engine(db_path: str | Path | None = None) -> Any | None:
    """Lazy-load the CaptureEngine."""
    try:
        from src.learning.capture_engine import CaptureEngine
        return CaptureEngine(db_path=db_path)
    except Exception:
        return None


def _load_data() -> dict[str, Any]:
    """Load all dashboard data from the CaptureEngine database."""
    from src.learning.forge_dashboard import (
        _compute_rolling_average,
        _get_db_path,
        _query_acceptance_rate,
        _query_language_breakdown,
        _query_session_stats,
        _query_signal_breakdown,
        _query_training_runs,
    )

    db_path = _get_db_path()
    result = {
        "daily": [],
        "rolling": [],
        "breakdown": {},
        "languages": [],
        "runs": [],
        "sessions": {"total_signals": 0, "total_sessions": 0, "unique_developers": 0,
                     "total_accepts": 0, "total_rejects": 0, "overall_rate": 0},
        "db_exists": db_path.exists(),
        "db_path": str(db_path),
    }

    if not db_path.exists():
        return result

    try:
        result["daily"] = _query_acceptance_rate(db_path, weeks=12)
        result["rolling"] = _compute_rolling_average(result["daily"])
        result["breakdown"] = _query_signal_breakdown(db_path)
        result["languages"] = _query_language_breakdown(db_path, limit=10)
        result["runs"] = _query_training_runs(db_path)
        result["sessions"] = _query_session_stats(db_path)
    except Exception as e:
        st.error(f"Failed to load dashboard data: {e}")

    return result


def render() -> None:
    """Render the ForgeAI acceptance rate dashboard page."""
    inject_dashboard_css()

    st.title("ForgeAI — Acceptance Rate Dashboard")
    st.caption("12-Week Self-Improvement Tracking · Powered by MIT SEAL Architecture")

    # ── Data Source Config ──
    with st.expander("Signal Database Configuration", expanded=False):
        from src.learning.forge_dashboard import _get_db_path
        db_path = _get_db_path()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.code(str(db_path))
        with col2:
            if db_path.exists():
                size_mb = db_path.stat().st_size / 1024 / 1024
                st.success(f"Exists ({size_mb:.1f} MB)")
            else:
                st.warning("Not found")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Refresh Data", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        with col_b:
            if st.button("Generate Demo Dashboard", use_container_width=True):
                from src.learning.forge_dashboard import generate_dashboard
                html = generate_dashboard(demo=True)
                st.session_state.forge_demo_html = html
                st.toast("Demo dashboard generated!", icon="[OK]")

        # Generate & open HTML dashboard button
        if st.button("📊 Open Full HTML Dashboard", use_container_width=True):
            from src.learning.forge_dashboard import generate_dashboard
            output = Path(db_path.parent) / "forge_dashboard.html"
            generate_dashboard(output_path=str(output))
            html_dashboard = open_html = str(output.resolve())
            st.markdown(f"Dashboard saved to: `{html_dashboard}`")
            st.toast(f"Dashboard saved to {output.name}", icon="[OK]")

    # Show cached or fresh demo HTML
    if st.session_state.get("forge_demo_html"):
        with st.expander("Demo Dashboard Preview", expanded=False):
            st.components.v1.html(st.session_state.forge_demo_html, height=600, scrolling=True)

    # ── Load Data ──
    data = _load_data()

    if not data["db_exists"] and "forge_demo_html" not in st.session_state:
        st.info(
            "📭 **No signal data found.** "
            "The CaptureEngine database doesn't exist yet.\n\n"
            "Start collecting signals by using `CaptureEngine` in your code:\n"
            "```python\n"
            "from src.learning.capture_engine import CaptureEngine\n"
            "engine = CaptureEngine()\n"
            "engine.capture_accept(suggestion, file_path, line_number, language)\n"
            "```\n\n"
            "Or click **Generate Demo Dashboard** above to see a preview with synthetic data."
        )
        return

    sessions = data["sessions"]
    daily = data["daily"]
    runs = data["runs"]

    # ── Key Metrics Row ──
    cols = st.columns(6)
    metric_card(cols[0], "Acceptance Rate", f"{sessions['overall_rate']}%", "All time")
    metric_card(cols[1], "Total Accepts", str(sessions["total_accepts"]), "Across all sessions")
    metric_card(cols[2], "Total Signals", str(sessions["total_signals"]), "All types")
    metric_card(cols[3], "Sessions", str(sessions["total_sessions"]), "Developer sessions")
    metric_card(cols[4], "Developers", str(sessions["unique_developers"]), "Unique devs")
    metric_card(cols[5], "Training Runs", str(len(runs)), "Model fine-tunes")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Acceptance Rate Chart ──
    if daily:
        st.subheader("📈 Acceptance Rate — 12 Weeks (Daily + 7-Day Rolling Avg)")

        chart_data = []
        for i, d in enumerate(daily):
            chart_data.append({
                "date": d["date"],
                "daily_rate": d["acceptance_rate"],
                "rolling_avg": data["rolling"][i] if i < len(data["rolling"]) and data["rolling"][i] is not None else None,
            })

        # Convert to Streamlit-friendly format
        chart_dates = [d["date"] for d in daily]
        chart_rates = [d["acceptance_rate"] for d in daily]
        chart_rolling = [r if r is not None else None for r in data["rolling"]]

        import pandas as pd
        df = pd.DataFrame({
            "date": chart_dates,
            "Daily Rate (%)": chart_rates,
            "7-Day Avg (%)": chart_rolling,
        })

        st.line_chart(
            df.set_index("date"),
            use_container_width=True,
            height=400,
        )

        st.caption(f"Showing {len(daily)} days of data. Each point represents one day's acceptance rate.")
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts Grid ──
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🧩 Signal Type Breakdown")
        breakdown = data["breakdown"]
        if breakdown:
            signal_type_order = ["accept", "reject", "edit", "test_pass", "test_fail", "pr_merge"]
            bdf = pd.DataFrame({
                "Type": [s.capitalize() for s in signal_type_order if breakdown.get(s, 0) > 0],
                "Count": [breakdown.get(s, 0) for s in signal_type_order if breakdown.get(s, 0) > 0],
            }).set_index("Type")
            st.bar_chart(bdf, use_container_width=True, height=300)
        else:
            st.info("No signal data to display.")

    with col_right:
        st.subheader("🌐 Signals by Language")
        lang_data = data["languages"]
        if lang_data:
            ldf = pd.DataFrame(
                {"Language": [l["language"] for l in lang_data],
                 "Count": [l["count"] for l in lang_data]}
            ).set_index("Language")
            st.bar_chart(ldf, use_container_width=True, height=300)
        else:
            st.info("No language data to display.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Training Run History ──
    st.subheader("🏋️ Training Run History")

    if runs:
        run_df = pd.DataFrame(runs)
        run_df["date"] = pd.to_datetime(run_df["date"])

        # Summary metrics for runs
        if run_df["rate_before"].notna().any() and run_df["rate_after"].notna().any():
            run_df["delta"] = run_df["rate_after"] - run_df["rate_before"]
            avg_improvement = run_df["delta"].mean()
            best_run = run_df.loc[run_df["delta"].idxmax()] if run_df["delta"].notna().any() else None

            met_cols = st.columns(3)
            met_cols[0].metric("Avg Acceptance Improvement", f"{avg_improvement:+.1f}%")
            if best_run is not None:
                met_cols[1].metric("Best Run", f"{best_run.get('delta', '—'):+.1f}%",
                                   help=f"Run: {best_run.get('date', '?')}")
            met_cols[2].metric("Total Runs", str(len(runs)))

        st.dataframe(
            run_df[["date", "model", "signals_used", "train_loss", "eval_loss",
                    "rate_before", "rate_after"]],
            use_container_width=True,
            column_config={
                "date": "Date",
                "model": "Model",
                "signals_used": st.column_config.NumberColumn("Signals", format="%d"),
                "train_loss": st.column_config.NumberColumn("Train Loss", format="%.4f"),
                "eval_loss": st.column_config.NumberColumn("Eval Loss", format="%.4f"),
                "rate_before": st.column_config.NumberColumn("Rate Before %", format="%.1f"),
                "rate_after": st.column_config.NumberColumn("Rate After %", format="%.1f"),
            },
            hide_index=True,
        )

        # Run improvement chart
        if "delta" in run_df.columns and run_df["delta"].notna().any():
            st.subheader("📊 Acceptance Delta per Training Run")
            delta_df = run_df[["date", "delta"]].dropna().set_index("date")
            st.bar_chart(delta_df, use_container_width=True, height=250)
    else:
        st.info("No training runs recorded yet. Run fine-tuning with the CaptureEngine to populate this table.")
